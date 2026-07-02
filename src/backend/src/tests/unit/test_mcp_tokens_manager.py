"""
Unit tests for MCPTokensManager's service-principal-only enforcement.

MCP tokens (mcp_tokens table) are for service-principal/M2M callers only as
of docs/notes/MCP_AUTH_REWORK_PRD.md - human callers authenticate via
forwarded-identity (OBO) auth instead. generate_token() must reject
is_service_principal=False rather than silently minting a human-equivalent
token, and every generated/validated token must carry is_service_principal
through end to end.
"""
import pytest

from src.controller.mcp_tokens_manager import MCPTokensManager


class TestMCPTokensManagerServicePrincipalOnly:
    def test_generate_token_defaults_to_service_principal(self, db_session):
        manager = MCPTokensManager(db=db_session)

        generated = manager.generate_token(name="test-token", scopes=["contracts:read"])

        assert generated.is_service_principal is True
        assert generated.token.startswith("mcp_")

    def test_generate_token_rejects_non_service_principal(self, db_session):
        manager = MCPTokensManager(db=db_session)

        with pytest.raises(ValueError, match="service-principal"):
            manager.generate_token(
                name="test-token", scopes=["contracts:read"], is_service_principal=False
            )

    def test_validate_token_carries_is_service_principal(self, db_session):
        manager = MCPTokensManager(db=db_session)
        # expires_days=None avoids a pre-existing, unrelated naive/aware
        # datetime comparison issue in MCPTokenDb.is_expired against the
        # SQLite test DB - not something this test is exercising.
        generated = manager.generate_token(
            name="test-token", scopes=["contracts:read"], expires_days=None
        )
        db_session.commit()

        validated = manager.validate_token(generated.token)

        assert validated is not None
        assert validated.is_service_principal is True

    def test_get_token_returns_the_created_token(self, db_session):
        """get_token() returns the raw MCPTokenDb row, which has no
        is_service_principal column - that's a fixed API-layer constant
        (models/mcp_tokens.py, mcp_tokens_routes.py), not persisted data.
        See db_models/mcp_tokens.py for why."""
        manager = MCPTokensManager(db=db_session)
        generated = manager.generate_token(name="test-token", scopes=["contracts:read"])
        db_session.commit()

        fetched = manager.get_token(generated.id)

        assert fetched is not None
        assert fetched.id == generated.id
        assert fetched.name == "test-token"
