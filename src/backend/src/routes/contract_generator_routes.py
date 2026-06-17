"""AI contract generator endpoints.

POST /api/contract-generator/preview  → inspect + LLM call, return draft contract (no DB write)
POST /api/contract-generator/generate → preview + persist as a draft DataContract
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from src.common.authorization import PermissionChecker
from src.common.dependencies import CurrentUserDep, DBSessionDep
from src.common.features import FeatureAccessLevel
from src.common.manager_dependencies import (
    get_contract_generator_manager,
    get_data_contracts_manager,
)
from src.controller.contract_generator_manager import ContractGeneratorManager
from src.controller.data_contracts_manager import DataContractsManager
from src.controller.llm_search_manager import get_session_store
from src.models.llm_search import MessageRole
from src.common.logging import get_logger

router = APIRouter(prefix="/api/contract-generator", tags=["contract-generator"])
logger = get_logger(__name__)


class GenerateRequest(BaseModel):
    catalog: str = Field(..., min_length=1, description="Unity Catalog catalog name")
    schema_: str = Field(..., min_length=1, alias="schema", description="Schema name")
    table: str = Field(..., min_length=1, description="Table name")
    sample_size: int = Field(20, ge=1, le=200, description="Rows to sample for LLM context")
    force: bool = Field(False, description="Regenerate even if a contract for this table already exists")
    # Optional Ask Ontos copilot session to record this draft turn into, so a
    # contract-draft turn lands in llm_sessions exactly like a chat turn. When
    # omitted (e.g. preview/generate non-copilot callers) no session is touched.
    session_id: Optional[str] = Field(None, description="Ask Ontos copilot session to record this draft turn into")

    model_config = {"populate_by_name": True}


def _user_token(x_forwarded_access_token: Optional[str]) -> Optional[str]:
    return x_forwarded_access_token or None


@router.post("/preview")
async def preview_contract(
    body: GenerateRequest,
    gen: ContractGeneratorManager = Depends(get_contract_generator_manager),
    x_forwarded_access_token: Optional[str] = Header(default=None),
    _: bool = Depends(PermissionChecker('data-contracts', FeatureAccessLevel.READ_WRITE)),
):
    """Generate a draft contract and return it WITHOUT persisting."""
    try:
        result = gen.generate(
            catalog=body.catalog,
            schema=body.schema_,
            table=body.table,
            sample_size=body.sample_size,
            user_token=_user_token(x_forwarded_access_token),
        )
    except ValueError as e:
        # Identifier validation failure or similar bad-input from the manager.
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        logger.warning(f"Contract generation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "contract": result.contract,
        "llm_model": result.llm_model,
        "duration_seconds": result.duration_seconds,
        "steps": result.steps,
        "warnings": result.warnings,
    }


@router.post("/generate", status_code=201)
async def generate_and_save(
    body: GenerateRequest,
    request: Request,
    db: DBSessionDep,
    gen: ContractGeneratorManager = Depends(get_contract_generator_manager),
    x_forwarded_access_token: Optional[str] = Header(default=None),
    _: bool = Depends(PermissionChecker('data-contracts', FeatureAccessLevel.READ_WRITE)),
):
    """Generate a draft contract and persist it."""
    try:
        current_user = None
        # Best-effort extract username from request state (set by auth middleware if present).
        user = getattr(request.state, "user", None)
        if user:
            current_user = getattr(user, "username", None) or getattr(user, "email", None)
        result = gen.generate_and_save(
            db=db,
            catalog=body.catalog,
            schema=body.schema_,
            table=body.table,
            sample_size=body.sample_size,
            current_user=current_user,
            user_token=_user_token(x_forwarded_access_token),
            force=body.force,
        )
    except ValueError as e:
        # Identifier validation failure or similar bad-input from the manager.
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        logger.warning(f"Contract generation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Contract generation failed")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
    return result


def _summarize_draft_turn(catalog: str, schema: str, table: str, terminal: Optional[dict]) -> str:
    """Build the assistant summary persisted into llm_sessions for a draft turn.

    Mirrors what the copilot panel renders so the recorded history reads like a
    chat turn: a short headline plus (on success) a link to the drafted contract.
    """
    fqn = f"{catalog}.{schema}.{table}"
    if not terminal:
        return f"Drafted a data contract for `{fqn}`."
    ttype = terminal.get("type")
    if ttype == "result":
        contract = terminal.get("contract") or {}
        name = contract.get("name") if isinstance(contract, dict) else None
        version = contract.get("version") if isinstance(contract, dict) else None
        contract_id = terminal.get("contract_id")
        label = f"`{name}`" if name else f"a data contract for `{fqn}`"
        if version:
            label += f" v{version}"
        summary = f"Drafted {label}."
        if contract_id:
            summary += f"\n\n[Open draft in contract editor](/data-contracts/{contract_id}?ai-draft=true)"
        return summary
    if ttype == "exists":
        return terminal.get("message") or f"A contract for `{fqn}` already exists."
    if ttype == "error":
        return f"⚠️ Contract draft for `{fqn}` failed: {terminal.get('message', 'Unknown error')}"
    return f"Drafted a data contract for `{fqn}`."


@router.post("/stream")
async def stream_contract(
    body: GenerateRequest,
    request: Request,
    db: DBSessionDep,
    current_user: CurrentUserDep,
    gen: ContractGeneratorManager = Depends(get_contract_generator_manager),
    x_forwarded_access_token: Optional[str] = Header(default=None),
    _: bool = Depends(PermissionChecker('data-contracts', FeatureAccessLevel.READ_WRITE)),
):
    """Stream contract-drafting progress as Server-Sent Events.

    Yields the generator's stage checklist + the LLM tokens live, then a terminal
    ``result`` (or ``exists`` / ``error``) event. Consumed by the Ask Ontos copilot
    panel. The SSE ``event:`` field carries the event type (stage|token|result|
    exists|error) and ``data:`` is the JSON payload.

    When the caller is the Ask Ontos copilot it threads a ``session_id`` (or none
    on the first turn); we record the draft turn into ``llm_sessions`` via the same
    ``DatabaseSessionStore`` the chat path uses, so the turn shows up in the copilot
    history and survives reload. A ``session`` event is emitted first carrying the
    resolved session id so the panel can adopt it.
    """
    import anyio
    from sse_starlette.sse import EventSourceResponse

    user_token = _user_token(x_forwarded_access_token)
    # The drafted DataContract's owner/author comes from request.state if present;
    # the llm-session owner is always the authenticated user (email), matching the
    # chat path's user_id so the turn lands in *this* user's history.
    contract_author = None
    state_user = getattr(request.state, "user", None)
    if state_user:
        contract_author = getattr(state_user, "username", None) or getattr(state_user, "email", None)
    session_user_id = current_user.email
    contract_author = contract_author or session_user_id

    # Resolve/create the copilot session and record the user prompt BEFORE
    # streaming, so the session id can be surfaced immediately and we never touch
    # the shared db session concurrently with the worker thread (which writes the
    # drafted contract). The assistant summary is persisted AFTER the stream drains.
    session_store = get_session_store()
    recorded_session_id: Optional[str] = None
    if body.session_id is not None:
        try:
            # Empty string => first copilot turn, create a session; a real id
            # continues an existing one (falling back to create if it's gone or
            # not owned by this user).
            session = None
            if body.session_id:
                session = session_store.get_for_user(db, body.session_id, session_user_id)
            if session is None:
                session = session_store.create(db, session_user_id)
            recorded_session_id = session.id
            user_prompt = f"Draft a data contract for {body.catalog}.{body.schema_}.{body.table}"
            session_store.add_message(db, recorded_session_id, MessageRole.USER, content=user_prompt)
        except Exception:
            logger.exception("Failed to record copilot user message for contract draft")
            recorded_session_id = None

    async def event_publisher():
        # Bounded buffer gives natural backpressure: the worker thread blocks on
        # send() when the client is slow; closing the receive end on disconnect
        # makes the blocked send raise (no deadlock).
        send_stream, receive_stream = anyio.create_memory_object_stream(max_buffer_size=200)

        def _run_blocking():
            try:
                for ev in gen.generate_stream(
                    catalog=body.catalog,
                    schema=body.schema_,
                    table=body.table,
                    sample_size=body.sample_size,
                    user_token=user_token,
                    db=db,
                    current_user=contract_author,
                    force=body.force,
                ):
                    anyio.from_thread.run(send_stream.send, ev)
            except Exception as e:  # never let the worker die silently
                logger.exception("Contract stream generation failed")
                try:
                    anyio.from_thread.run(send_stream.send, {"type": "error", "message": str(e)})
                except Exception:
                    pass
            finally:
                anyio.from_thread.run(send_stream.aclose)

        # Surface the resolved copilot session id up front so the panel can adopt
        # it (mirrors chat's response.session_id) before any tokens arrive.
        if recorded_session_id:
            yield {"event": "session", "data": json.dumps({"session_id": recorded_session_id})}

        terminal_ev: Optional[dict] = None
        client_gone = False
        async with anyio.create_task_group() as tg:
            tg.start_soon(anyio.to_thread.run_sync, _run_blocking)
            async with receive_stream:
                async for ev in receive_stream:
                    if await request.is_disconnected():
                        client_gone = True
                        break
                    if ev.get("type") in ("result", "exists", "error"):
                        terminal_ev = ev
                    yield {"event": ev.get("type", "message"), "data": json.dumps(ev)}

        # Persist the assistant summary AFTER the worker has finished writing the
        # contract (stream drained) so we don't race on the shared db session.
        if recorded_session_id and not client_gone:
            try:
                summary = _summarize_draft_turn(body.catalog, body.schema_, body.table, terminal_ev)
                session_store.add_message(
                    db, recorded_session_id, MessageRole.ASSISTANT, content=summary
                )
            except Exception:
                logger.exception("Failed to record copilot assistant summary for contract draft")

    return EventSourceResponse(
        event_publisher(),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def register_routes(app):
    """Standard registration entrypoint used by app.py."""
    app.include_router(router)
