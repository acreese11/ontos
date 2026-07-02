"""
FastAPI routes for MCP (Model Context Protocol) server.

Implements a JSON-RPC 2.0 endpoint for MCP clients to interact with application tools.
Supports both standard HTTP POST/JSON responses and SSE (Server-Sent Events) transport.

Auth model (see docs/notes/MCP_AUTH_REWORK_PRD.md for full design/rationale):
  1. Forwarded-identity (OBO) - preferred. Resolved from the same
     X-Forwarded-Access-Token/X-Forwarded-Email headers Databricks Apps
     injects for every other route (common/authorization.py). MCP tool
     access is gated by the caller's real Ontos FeatureAccessLevel
     permissions (common/mcp_permissions.py), not a separate scope system.
  2. X-API-Key / mcp_tokens - fallback for service-principal/M2M callers with
     no human to act on behalf of. Cannot be used behind a Unity Catalog HTTP
     connection (see PRD §4.2) - only for direct/bespoke HTTP callers.
"""

import asyncio
import json
import secrets
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from src.common.config import Settings, get_settings
from src.common.database import get_db
from src.common.dependencies import AuditManagerDep
from src.common.logging import get_logger
from src.common.mcp_permissions import get_effective_permissions_for_mcp, identity_has_scope
from src.controller.audit_manager import AuditManager
from src.controller.mcp_tokens_manager import MCPTokensManager, MCPTokenInfo
from src.models.mcp import JSONRPCRequest, JSONRPCError, JSONRPCResponse
from src.models.users import UserInfo
from src.tools.base import ToolContext, ToolResult
from src.tools.registry import create_default_registry

# MCPCaller: either a resolved human identity (forwarded-identity/OBO auth -
# the preferred path, gated by the caller's real Ontos permissions) or a
# service-principal token (M2M fallback for callers with no human to act on
# behalf of). See docs/notes/MCP_AUTH_REWORK_PRD.md.
MCPCaller = Union[UserInfo, MCPTokenInfo]

logger = get_logger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["MCP Server"])


def register_routes(app):
    """Register MCP routes with the FastAPI app."""
    app.include_router(router)


# JSON-RPC 2.0 Error Codes
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603

# Custom MCP Error Codes
MCP_AUTH_FAILED = -32001
MCP_AUTH_MISSING_SCOPE = -32002

# MCP Protocol Version
MCP_PROTOCOL_VERSION = "2024-11-05"

# Feature ID for audit logging
MCP_FEATURE_ID = "mcp"

# Session storage (in-memory for now, could be moved to Redis/DB for production)
_sessions: Dict[str, Dict[str, Any]] = {}


def make_error_response(
    code: int,
    message: str,
    data: Any = None,
    request_id: Optional[Union[str, int]] = None
) -> JSONRPCResponse:
    """Create a JSON-RPC error response."""
    return JSONRPCResponse(
        error=JSONRPCError(code=code, message=message, data=data),
        id=request_id
    )


def make_success_response(
    result: Any,
    request_id: Optional[Union[str, int]] = None
) -> JSONRPCResponse:
    """Create a JSON-RPC success response."""
    return JSONRPCResponse(result=result, id=request_id)


def generate_session_id() -> str:
    """Generate a cryptographically secure session ID."""
    return secrets.token_urlsafe(32)


def generate_event_id() -> str:
    """Generate a unique event ID for SSE resumability."""
    return f"evt_{secrets.token_urlsafe(16)}"


def caller_identity_key(caller: "MCPCaller") -> str:
    """Stable identity string for session binding.

    `_sessions` is an in-memory dict keyed only by an opaque session id -
    nothing previously bound a session to the caller that created it beyond
    knowledge of that id. This is used to detect (and reject) a session being
    reused by a different principal than the one that initialized it, e.g. a
    forwarded-identity session later replayed with an unrelated X-API-Key.
    """
    if isinstance(caller, UserInfo):
        return f"user:{caller.email}"
    return f"token:{caller.name}"


def wants_sse(request: Request) -> bool:
    """Whether to respond to this request with SSE instead of plain JSON.

    Always False for now. Databricks' MCP client (AI Gateway / Genie One /
    Playground) sends `Accept: text/event-stream` on every request regardless
    of whether it actually wants a stream, and empirically cannot correctly
    parse our SSE responses when assembling tool definitions for a live model
    invocation - confirmed via system.ai_gateway.usage: every single call from
    Databricks (including the `armeria` AI Gateway backend itself) got back
    `text/event-stream`, and tools never made it into an actual chat
    completion even though tool *browsing* (Catalog Explorer's "Edit tools"
    picker) worked fine. Another MCP server in this same account hit the
    identical problem and worked around it with a dedicated SSE->JSON
    "normalization" proxy app; forcing JSON here instead avoids needing one.

    The `request` parameter is unused now but kept so this can be reverted to
    real Accept-header sniffing if Databricks' client behavior changes.
    """
    return False


def format_sse_event(
    data: Dict[str, Any],
    event_id: Optional[str] = None,
    event_type: str = "message"
) -> Dict[str, Any]:
    """Format data as an SSE event dict for sse-starlette."""
    event = {
        "event": event_type,
        "data": json.dumps(data, default=str),
    }
    if event_id:
        event["id"] = event_id
    return event


class MCPHandler:
    """Handler for MCP JSON-RPC methods."""
    
    def __init__(
        self,
        db: Session,
        settings: Settings,
        caller: MCPCaller,
        request: Request,
        audit_manager: Optional[AuditManager] = None,
        session_id: Optional[str] = None,
        effective_permissions: Optional[Dict[str, Any]] = None,
    ):
        self._db = db
        self._settings = settings
        self._caller = caller
        # Only populated for UserInfo (identity-path) callers - resolved once
        # per request by the route handler before constructing this class, to
        # avoid opening a DB session per tool during tools/list filtering.
        # See common/mcp_permissions.get_effective_permissions_for_mcp.
        self._effective_permissions = effective_permissions or {}
        self._request = request
        self._audit_manager = audit_manager
        self._session_id = session_id
        self._tool_registry = create_default_registry()

    def _get_username(self) -> str:
        if isinstance(self._caller, UserInfo):
            return self._caller.email
        return self._caller.created_by or self._caller.name
    
    def _get_ip_address(self) -> Optional[str]:
        return self._request.client.host if self._request.client else None
    
    def _audit(self, *, action: str, success: bool, details: Optional[Dict[str, Any]] = None):
        """Log an audit record if audit manager is available."""
        if not self._audit_manager:
            return
        self._audit_manager.log_action(
            db=self._db,
            username=self._get_username(),
            ip_address=self._get_ip_address(),
            feature=MCP_FEATURE_ID,
            action=action,
            success=success,
            details=details,
        )
    
    async def handle(self, rpc_request: JSONRPCRequest) -> JSONRPCResponse:
        """Route the request to the appropriate handler."""
        method = rpc_request.method
        params = rpc_request.params or {}
        request_id = rpc_request.id
        
        handlers = {
            "initialize": self._handle_initialize,
            "notifications/initialized": self._handle_initialized,
            "ping": self._handle_ping,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
        }
        
        handler = handlers.get(method)
        if not handler:
            return make_error_response(
                JSONRPC_METHOD_NOT_FOUND,
                f"Method not found: {method}",
                request_id=request_id
            )
        
        try:
            result = await handler(params)
            return make_success_response(result, request_id=request_id)
        except MCPError as e:
            return make_error_response(e.code, e.message, e.data, request_id=request_id)
        except Exception as e:
            logger.error(f"Error handling MCP method {method}: {e}", exc_info=True)
            return make_error_response(
                JSONRPC_INTERNAL_ERROR,
                f"Internal error: {str(e)}",
                request_id=request_id
            )
    
    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request."""
        # Store client info in session if available
        client_info = params.get("clientInfo", {})
        if self._session_id and self._session_id in _sessions:
            _sessions[self._session_id]["client_info"] = client_info
            _sessions[self._session_id]["initialized"] = True
        
        self._audit(
            action="SESSION_CREATE",
            success=True,
            details={
                "session_id": self._session_id,
                "caller": self._get_username(),
                "client_info": client_info,
            },
        )
        
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "serverInfo": {
                "name": "ontos-mcp-server",
                "version": "1.0.0"
            },
            "capabilities": {
                "tools": {}
            }
        }
    
    async def _handle_initialized(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialized notification."""
        return {}
    
    async def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ping request."""
        return {"pong": True, "timestamp": datetime.now(timezone.utc).isoformat()}
    
    async def _handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/list request, filtering by token scopes."""
        all_tools = self._tool_registry.get_mcp_definitions()
        
        # Filter tools by scope
        filtered_tools = []
        for tool_def in all_tools:
            tool = self._tool_registry.get(tool_def["name"])
            if tool:
                required_scope = getattr(tool, "required_scope", "*")
                if self._has_scope(required_scope):
                    filtered_tools.append(tool_def)
        
        return {"tools": filtered_tools}
    
    async def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        
        if not tool_name:
            raise MCPError(JSONRPC_INVALID_PARAMS, "Missing tool name")
        
        # Get the tool
        tool = self._tool_registry.get(tool_name)
        if not tool:
            raise MCPError(JSONRPC_METHOD_NOT_FOUND, f"Tool not found: {tool_name}")
        
        # Check scope
        required_scope = getattr(tool, "required_scope", "*")
        if not self._has_scope(required_scope):
            caller_scopes = None if isinstance(self._caller, UserInfo) else self._caller.scopes
            self._audit(
                action="SCOPE_VIOLATION",
                success=False,
                details={
                    "tool_name": tool_name,
                    "required_scope": required_scope,
                    "caller_scopes": caller_scopes,
                    "caller": self._get_username(),
                    "session_id": self._session_id,
                },
            )
            raise MCPError(
                MCP_AUTH_MISSING_SCOPE,
                f"Missing required scope: {required_scope}",
                {"required_scope": required_scope, "token_scopes": caller_scopes}
            )

        # Create tool context
        ctx = self._create_tool_context()

        # Execute the tool with audit logging
        success = False
        details_for_audit: Dict[str, Any] = {
            "tool_name": tool_name,
            "caller": self._get_username(),
            "session_id": self._session_id,
        }
        try:
            result = await tool.execute(ctx, **tool_args)
            is_error = not result.success
            details_for_audit["is_error"] = is_error
            success = not is_error
            
            if result.success:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result.data, default=str)
                        }
                    ],
                    "isError": False
                }
            else:
                details_for_audit["tool_error"] = result.error
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": result.error or "Unknown error"
                        }
                    ],
                    "isError": True
                }
                
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            details_for_audit["exception"] = {"type": type(e).__name__, "message": str(e)}
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Tool execution failed: {str(e)}"
                    }
                ],
                "isError": True
            }
        finally:
            self._audit(action="TOOL_CALL", success=success, details=details_for_audit)
    
    def _has_scope(self, required_scope: str) -> bool:
        """Check if the caller (identity or token) has the required scope.

        Identity-path (UserInfo) callers are checked against their real Ontos
        permissions via the scope->feature mapping in common/mcp_permissions.py
        - this fails closed for any scope without a mapping (e.g. "analytics:*",
        "semantic:*"), rather than falling through to token-style wildcard
        matching. Token-path (MCPTokenInfo) callers keep the original
        scopes-array matching, unchanged, for the M2M fallback path.
        """
        if isinstance(self._caller, UserInfo):
            from src.common.manager_dependencies import get_auth_manager
            auth_manager = get_auth_manager(self._request)
            return identity_has_scope(self._effective_permissions, required_scope, auth_manager)

        scopes = self._caller.scopes

        # Admin wildcard
        if "*" in scopes:
            return True

        # Exact match
        if required_scope in scopes:
            return True

        # Prefix wildcard
        if ":" in required_scope:
            prefix = required_scope.split(":")[0]
            if f"{prefix}:*" in scopes:
                return True

        return False
    
    def _create_tool_context(self) -> ToolContext:
        """Create a ToolContext for tool execution."""
        # Get managers from app.state if available
        app = self._request.app
        
        return ToolContext(
            db=self._db,
            settings=self._settings,
            workspace_client=getattr(app.state, "workspace_client", None),
            data_products_manager=getattr(app.state, "data_products_manager", None),
            data_contracts_manager=getattr(app.state, "data_contracts_manager", None),
            semantic_models_manager=getattr(app.state, "semantic_models_manager", None),
            costs_manager=None,  # Add if needed
            search_manager=getattr(app.state, "search_manager", None)
        )


class MCPError(Exception):
    """MCP-specific error with JSON-RPC code."""
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


def validate_api_key(
    db: Session,
    x_api_key: Optional[str]
) -> Optional[MCPTokenInfo]:
    """Validate the API key and return token info if valid."""
    if not x_api_key:
        return None

    token_manager = MCPTokensManager(db=db)
    return token_manager.validate_token(x_api_key)


async def resolve_identity_caller(request: Request, settings: Settings) -> Optional[UserInfo]:
    """Best-effort resolution of a forwarded-identity (OBO) caller.

    Delegates to the same resolution logic every other route in the app uses
    (common.authorization.get_user_details_from_sdk) so MCP identity is
    verified the same way: in non-local environments this round-trips the
    `X-Forwarded-Access-Token` through `current_user.me()` against the real
    Databricks workspace - a forged token fails there, not at header
    inspection.

    Returns None (rather than raising) when there's no forwarded-identity
    signal on the request, so the caller can fall back to the M2M / X-API-Key
    path without this looking like an error. Local/mock-mode requests always
    resolve to the configured mock user, matching the rest of the app's
    local-dev behavior.
    """
    from src.common.authorization import get_user_details_from_sdk
    from src.common.manager_dependencies import get_users_manager

    is_local_or_mock = settings.ENV.upper().startswith("LOCAL") or getattr(settings, "MOCK_USER_DETAILS", False)
    if not is_local_or_mock:
        has_forwarded_identity = (
            request.headers.get("x-forwarded-access-token")
            or request.headers.get("X-Forwarded-Email")
            or request.headers.get("X-Forwarded-User")
        )
        if not has_forwarded_identity:
            return None

    try:
        manager = get_users_manager(request)
        return await get_user_details_from_sdk(request, settings, manager)
    except HTTPException as e:
        logger.warning(
            "MCP: forwarded-identity headers present but resolution failed (%s); "
            "falling back to X-API-Key auth if available",
            e.detail,
        )
        return None


async def resolve_mcp_caller(
    request: Request,
    db: Session,
    settings: Settings,
    x_api_key: Optional[str],
) -> Optional["MCPCaller"]:
    """Resolve the calling principal for an MCP request.

    Tries forwarded-identity (OBO) auth first - the preferred path, per
    docs/notes/MCP_AUTH_REWORK_PRD.md, gating MCP access by the caller's real
    Ontos permissions rather than a separate scope system. Falls back to the
    X-API-Key / mcp_tokens path for service-principal callers with no human to
    act on behalf of.
    """
    user_details = await resolve_identity_caller(request, settings)
    if user_details is not None:
        return user_details
    return validate_api_key(db, x_api_key)


async def sse_event_generator(
    response_data: Dict[str, Any],
    session_id: Optional[str] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """Generate SSE events for a single response."""
    # Send initial event with empty data to prime the connection (per MCP spec)
    event_id = generate_event_id()
    yield format_sse_event({}, event_id=event_id, event_type="open")
    
    # Send the actual response
    event_id = generate_event_id()
    yield format_sse_event(response_data, event_id=event_id, event_type="message")


async def sse_stream_generator(
    caller: "MCPCaller",
    session_id: str,
    request: Request
) -> AsyncGenerator[Dict[str, Any], None]:
    """Generate SSE events for an open stream (GET endpoint)."""
    # Send initial connection event
    event_id = generate_event_id()
    yield format_sse_event(
        {"type": "connection", "session_id": session_id},
        event_id=event_id,
        event_type="open"
    )
    
    # Keep the connection alive with periodic pings
    # This allows server-initiated messages in the future
    try:
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                logger.info(f"SSE client disconnected: session={session_id}")
                break
            
            # Send a keepalive ping every 30 seconds
            await asyncio.sleep(30)
            
            if session_id in _sessions:
                event_id = generate_event_id()
                yield format_sse_event(
                    {"type": "ping", "timestamp": datetime.now(timezone.utc).isoformat()},
                    event_id=event_id,
                    event_type="ping"
                )
    except asyncio.CancelledError:
        logger.info(f"SSE stream cancelled: session={session_id}")
    finally:
        # Clean up session on disconnect
        if session_id in _sessions:
            logger.info(f"Cleaning up session: {session_id}")


@router.get("")
async def mcp_sse_stream(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    mcp_session_id: Optional[str] = Header(None, alias="MCP-Session-Id"),
):
    """
    MCP SSE stream endpoint (GET).
    
    Opens a Server-Sent Events stream for server-to-client messages.
    Requires Accept: text/event-stream header.
    """
    # Check Accept header
    if not wants_sse(request):
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail="GET requires Accept: text/event-stream header"
        )
    
    # Resolve caller: forwarded-identity (OBO) first, X-API-Key (M2M) fallback.
    caller = await resolve_mcp_caller(request, db, settings, x_api_key)
    if not caller:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing credentials"
        )

    # Get or create session
    session_id = mcp_session_id
    if session_id and session_id not in _sessions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    identity_key = caller_identity_key(caller)
    if session_id and _sessions[session_id].get("identity_key") != identity_key:
        logger.warning(
            "MCP: session %s presented by a different caller than created it", session_id
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session identity mismatch")

    if not session_id:
        session_id = generate_session_id()
        _sessions[session_id] = {
            "created_at": datetime.now(timezone.utc),
            "identity_key": identity_key,
            "initialized": False
        }
        logger.info(f"Created new MCP session: {session_id}")

    # Return SSE stream
    return EventSourceResponse(
        sse_stream_generator(caller, session_id, request),
        headers={
            "MCP-Session-Id": session_id,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.post("")
async def mcp_handler(
    request: Request,
    audit_manager: AuditManagerDep,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    mcp_session_id: Optional[str] = Header(None, alias="MCP-Session-Id"),
    mcp_protocol_version: Optional[str] = Header(None, alias="MCP-Protocol-Version"),
):
    """
    MCP JSON-RPC 2.0 endpoint (POST).

    Auth: forwarded-identity (OBO) headers are tried first - the preferred
    path, gating access by the caller's real Ontos permissions (see
    docs/notes/MCP_AUTH_REWORK_PRD.md). Falls back to X-API-Key with a valid
    MCP token for service-principal/M2M callers.
    Supports methods: initialize, notifications/initialized, ping, tools/list, tools/call

    Response format depends on Accept header:
    - Accept: text/event-stream -> SSE stream response
    - Accept: application/json (or default) -> JSON response
    """
    use_sse = wants_sse(request)
    session_id = mcp_session_id
    
    # Helper to create error response in the appropriate format
    async def error_response(code: int, message: str, request_id: Any = None):
        response_data = JSONRPCResponse(
            error=JSONRPCError(code=code, message=message),
            id=request_id
        ).model_dump()
        
        if use_sse:
            return EventSourceResponse(
                sse_event_generator(response_data, session_id),
                headers={"MCP-Session-Id": session_id} if session_id else {}
            )
        return JSONResponse(content=response_data)
    
    # Resolve caller: forwarded-identity (OBO) first, X-API-Key (M2M) fallback.
    # See docs/notes/MCP_AUTH_REWORK_PRD.md - identity is the preferred path,
    # gating MCP access by the caller's real Ontos permissions.
    caller = await resolve_mcp_caller(request, db, settings, x_api_key)
    if not caller:
        audit_manager.log_action(
            db=db,
            username="anonymous",
            ip_address=request.client.host if request.client else None,
            feature=MCP_FEATURE_ID,
            action="AUTH_FAILURE",
            success=False,
            details={"reason": "Invalid or missing credentials"},
        )
        return await error_response(MCP_AUTH_FAILED, "Invalid or missing credentials")

    # Parse request body
    try:
        body = await request.json()
    except Exception as e:
        return await error_response(JSONRPC_PARSE_ERROR, f"Failed to parse JSON: {str(e)}")

    # Validate JSON-RPC format
    try:
        rpc_request = JSONRPCRequest(**body)
    except Exception as e:
        return await error_response(JSONRPC_INVALID_REQUEST, f"Invalid request: {str(e)}")

    # Handle session management
    is_initialize = rpc_request.method == "initialize"
    identity_key = caller_identity_key(caller)

    if is_initialize:
        # Create new session on initialize, bound to this caller's identity.
        session_id = generate_session_id()
        _sessions[session_id] = {
            "created_at": datetime.now(timezone.utc),
            "identity_key": identity_key,
            "initialized": False
        }
        logger.info(f"Created new MCP session on initialize: {session_id}")
    elif session_id:
        # Validate existing session
        if session_id not in _sessions:
            return await error_response(
                JSONRPC_INVALID_REQUEST,
                "Session not found",
                rpc_request.id
            )
        # Reject reuse of a session by a different principal than created it
        # (e.g. a forwarded-identity session replayed with an unrelated
        # X-API-Key) - see docs/notes/MCP_AUTH_REWORK_PRD.md §5.
        if _sessions[session_id].get("identity_key") != identity_key:
            logger.warning("MCP: session %s presented by a different caller than created it", session_id)
            return await error_response(JSONRPC_INVALID_REQUEST, "Session identity mismatch", rpc_request.id)

    # Log the request
    logger.info(f"MCP request: method={rpc_request.method}, caller={identity_key}, sse={use_sse}")

    # For identity-path callers, resolve effective permissions once per
    # request (not once per tool - see common/mcp_permissions.py for why).
    effective_permissions: Dict[str, Any] = {}
    if isinstance(caller, UserInfo):
        effective_permissions = await get_effective_permissions_for_mcp(caller, request)

    # Handle the request
    handler = MCPHandler(
        db, settings, caller, request, audit_manager, session_id,
        effective_permissions=effective_permissions,
    )
    response = await handler.handle(rpc_request)
    
    # Commit any changes
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Error committing MCP changes: {e}")
        db.rollback()
    
    response_data = response.model_dump()
    
    # Build response headers
    response_headers = {}
    if session_id:
        response_headers["MCP-Session-Id"] = session_id
    
    # Return in appropriate format
    if use_sse:
        return EventSourceResponse(
            sse_event_generator(response_data, session_id),
            headers=response_headers
        )
    
    return JSONResponse(content=response_data, headers=response_headers)


@router.delete("")
async def mcp_delete_session(
    request: Request,
    audit_manager: AuditManagerDep,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    mcp_session_id: Optional[str] = Header(None, alias="MCP-Session-Id"),
):
    """
    Delete an MCP session.

    Clients should call this when they no longer need the session.
    """
    # Resolve caller: forwarded-identity (OBO) first, X-API-Key (M2M) fallback.
    caller = await resolve_mcp_caller(request, db, settings, x_api_key)
    if not caller:
        audit_manager.log_action(
            db=db,
            username="anonymous",
            ip_address=request.client.host if request.client else None,
            feature=MCP_FEATURE_ID,
            action="AUTH_FAILURE",
            success=False,
            details={"reason": "Invalid or missing credentials", "endpoint": "DELETE"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing credentials"
        )

    if not mcp_session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MCP-Session-Id header required"
        )

    if mcp_session_id in _sessions:
        if _sessions[mcp_session_id].get("identity_key") != caller_identity_key(caller):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session identity mismatch")
        del _sessions[mcp_session_id]
        logger.info(f"Deleted MCP session: {mcp_session_id}")
        audit_manager.log_action(
            db=db,
            username=caller.email if isinstance(caller, UserInfo) else (caller.created_by or caller.name),
            ip_address=request.client.host if request.client else None,
            feature=MCP_FEATURE_ID,
            action="SESSION_DELETE",
            success=True,
            details={"session_id": mcp_session_id, "caller": caller_identity_key(caller)},
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Session not found"
    )


@router.get("/health")
async def mcp_health():
    """Health check endpoint for MCP server."""
    return {
        "status": "ok",
        "server": "ontos-mcp-server",
        "version": "1.0.0",
        "protocol_version": MCP_PROTOCOL_VERSION,
        "active_sessions": len(_sessions)
    }
