"""
Unit tests for common/mcp_permissions.py

Tests the scope->feature mapping used by identity-path (OBO) MCP callers:
- Mapped scopes (contracts:read/write/delete) resolve to the correct
  (feature_id, FeatureAccessLevel) pair
- Unmapped scopes (analytics, semantic, etc.) fail closed - no mapping,
  no access - rather than defaulting open
- identity_has_scope() correctly delegates to AuthorizationManager.has_permission
  for mapped scopes, and denies unmapped scopes without calling it at all

See docs/notes/MCP_AUTH_REWORK_PRD.md for the design this implements.
"""
from unittest.mock import Mock

import pytest

from src.common.features import FeatureAccessLevel
from src.common.mcp_permissions import identity_has_scope, scope_to_feature_requirement


class TestScopeToFeatureRequirement:
    """Mapped scopes resolve correctly; unmapped scopes return None."""

    @pytest.mark.parametrize(
        "scope,expected_feature,expected_level",
        [
            ("contracts:read", "data-contracts", FeatureAccessLevel.READ_ONLY),
            ("contracts:write", "data-contracts", FeatureAccessLevel.READ_WRITE),
            ("contracts:delete", "data-contracts", FeatureAccessLevel.ADMIN),
        ],
    )
    def test_mapped_scopes(self, scope, expected_feature, expected_level):
        result = scope_to_feature_requirement(scope)
        assert result == (expected_feature, expected_level)

    @pytest.mark.parametrize(
        "scope",
        [
            "analytics:read",
            "costs:read",
            "semantic:read",
            "semantic:write",
            "sparql:query",
            "user:read",
            "search:read",
            "tags:read",
            "tags:write",
            "domains:read",
            "teams:read",
            "projects:read",
            "data-products:read",
            "*",
            "unknown:scope",
        ],
    )
    def test_unmapped_scopes_return_none(self, scope):
        """Deliberately unmapped for v1 (PRD §4.0/§4.1) - must fail closed, not default open."""
        assert scope_to_feature_requirement(scope) is None


class TestIdentityHasScope:
    """identity_has_scope() gates on the mapping, delegating to has_permission only when mapped."""

    def test_mapped_scope_delegates_to_auth_manager(self):
        auth_manager = Mock()
        auth_manager.has_permission.return_value = True
        effective_permissions = {"data-contracts": FeatureAccessLevel.READ_WRITE}

        result = identity_has_scope(effective_permissions, "contracts:write", auth_manager)

        assert result is True
        auth_manager.has_permission.assert_called_once_with(
            effective_permissions, "data-contracts", FeatureAccessLevel.READ_WRITE
        )

    def test_mapped_scope_denied_when_auth_manager_denies(self):
        auth_manager = Mock()
        auth_manager.has_permission.return_value = False
        effective_permissions = {"data-contracts": FeatureAccessLevel.READ_ONLY}

        result = identity_has_scope(effective_permissions, "contracts:delete", auth_manager)

        assert result is False
        auth_manager.has_permission.assert_called_once_with(
            effective_permissions, "data-contracts", FeatureAccessLevel.ADMIN
        )

    def test_read_write_user_cannot_delete(self):
        """The delete-vs-standard-write split: READ_WRITE must not satisfy the ADMIN-gated delete scope.

        Uses the real has_permission-equivalent comparison semantics (mocked here
        to isolate identity_has_scope, but mirrors AuthorizationManager.has_permission's
        ACCESS_LEVEL_ORDER comparison) to confirm delete requires strictly more
        than READ_WRITE - see tools/data_contracts.py DeleteDataContractTool and
        PRD §4.1's collapsed-scope regression finding.
        """
        auth_manager = Mock()
        # Simulate real has_permission ordering behavior for this specific case.
        auth_manager.has_permission.side_effect = lambda perms, feature, level: (
            perms.get(feature, FeatureAccessLevel.NONE) == FeatureAccessLevel.ADMIN
            if level == FeatureAccessLevel.ADMIN
            else True
        )
        effective_permissions = {"data-contracts": FeatureAccessLevel.READ_WRITE}

        assert identity_has_scope(effective_permissions, "contracts:write", auth_manager) is True
        assert identity_has_scope(effective_permissions, "contracts:delete", auth_manager) is False

    def test_unmapped_scope_denied_without_calling_auth_manager(self):
        """Unmapped scopes fail closed and short-circuit before touching AuthorizationManager at all."""
        auth_manager = Mock()

        result = identity_has_scope({"data-contracts": FeatureAccessLevel.ADMIN}, "analytics:read", auth_manager)

        assert result is False
        auth_manager.has_permission.assert_not_called()

    def test_empty_permissions_denied_for_mapped_scope(self):
        auth_manager = Mock()
        auth_manager.has_permission.return_value = False

        result = identity_has_scope({}, "contracts:read", auth_manager)

        assert result is False
