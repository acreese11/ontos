"""
Unit tests for pure-function helpers in routes/mcp_routes.py.

Regression coverage for two bugs found in code review of the MCP
identity-auth rework (PR #69):
  1. `wants_sse` / `post_wants_sse` must be independent - collapsing them
     into one always-False function silently 405'd the GET SSE-stream
     endpoint regardless of Accept header (no test caught this originally).
  2. `caller_identity_key` must key M2M sessions on the token's unique id,
     not its user-chosen (non-unique) display name.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from src.controller.mcp_tokens_manager import MCPTokenInfo
from src.models.users import UserInfo
from src.routes.mcp_routes import caller_identity_key, post_wants_sse, wants_sse


def _mock_request(accept: str = "") -> MagicMock:
    request = MagicMock()
    request.headers = {"accept": accept}
    return request


class TestWantsSse:
    """GET /api/mcp stream endpoint should still honor a real Accept header."""

    def test_get_stream_honors_sse_accept_header(self):
        assert wants_sse(_mock_request("text/event-stream")) is True

    def test_get_stream_rejects_non_sse_accept_header(self):
        assert wants_sse(_mock_request("application/json")) is False

    def test_get_stream_rejects_missing_accept_header(self):
        assert wants_sse(_mock_request("")) is False


class TestPostWantsSse:
    """POST /api/mcp always responds JSON regardless of Accept header.

    (Databricks' MCP client sends `Accept: text/event-stream` on every POST
    but cannot consume an SSE response - see post_wants_sse's docstring.)
    """

    def test_post_ignores_sse_accept_header(self):
        assert post_wants_sse(_mock_request("text/event-stream")) is False

    def test_post_ignores_json_accept_header(self):
        assert post_wants_sse(_mock_request("application/json")) is False


class TestCallerIdentityKey:
    def test_user_caller_keyed_by_email(self):
        caller = UserInfo(email="alice@example.com", username="alice", user="alice", ip="1.2.3.4")
        assert caller_identity_key(caller) == "user:alice@example.com"

    def test_token_caller_keyed_by_unique_id_not_name(self):
        """Two tokens with the same display name must not collide.

        MCPTokenDb.name has no unique constraint (only token_hash does), so
        keying on name would let a session created by one token be presented
        with a different token sharing the same name, defeating the
        session-identity-mismatch check this key exists for.
        """
        common_name = "Genie Integration"
        token_a = MCPTokenInfo(
            id=uuid4(),
            name=common_name,
            scopes=["contracts:read"],
            created_by="alice@example.com",
            created_at=datetime.now(timezone.utc),
            expires_at=None,
        )
        token_b = MCPTokenInfo(
            id=uuid4(),
            name=common_name,
            scopes=["contracts:read"],
            created_by="bob@example.com",
            created_at=datetime.now(timezone.utc),
            expires_at=None,
        )
        assert caller_identity_key(token_a) != caller_identity_key(token_b)
        assert caller_identity_key(token_a) == f"token:{token_a.id}"
