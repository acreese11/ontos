"""
Unit tests for AuthorizationManager

Tests authorization and permission management including:
- Effective permission calculation
- Permission merging from multiple roles
- Team role overrides
- Access level checking
"""
import pytest
import uuid
from unittest.mock import Mock

from src.controller.authorization_manager import AuthorizationManager
from src.models.settings import AppRole
from src.common.features import FeatureAccessLevel


class TestAuthorizationManager:
    """Test suite for AuthorizationManager"""

    @pytest.fixture
    def mock_settings_manager(self):
        """Create a mock SettingsManager."""
        return Mock()

    @pytest.fixture
    def manager(self, mock_settings_manager):
        """Create AuthorizationManager instance for testing."""
        return AuthorizationManager(settings_manager=mock_settings_manager)

    @pytest.fixture
    def developer_role(self):
        """Create a developer role with basic permissions."""
        return AppRole(
            id=uuid.uuid4(),
            name="Developer",
            description="Developer role",
            assigned_groups=["developers"],
            feature_permissions={
                "data-products": FeatureAccessLevel.READ_WRITE,
                "data-contracts": FeatureAccessLevel.READ_WRITE,
                "teams": FeatureAccessLevel.READ_ONLY,
            },
            home_sections=[],
            approval_privileges={},
        )

    @pytest.fixture
    def admin_role(self):
        """Create an admin role with full permissions."""
        return AppRole(
            id=uuid.uuid4(),
            name="Admin",
            description="Admin role",
            assigned_groups=["admins"],
            feature_permissions={
                "data-products": FeatureAccessLevel.ADMIN,
                "data-contracts": FeatureAccessLevel.ADMIN,
                "teams": FeatureAccessLevel.ADMIN,
                "settings": FeatureAccessLevel.ADMIN,
            },
            home_sections=[],
            approval_privileges={},
        )

    @pytest.fixture
    def viewer_role(self):
        """Create a viewer role with read-only permissions."""
        return AppRole(
            id=uuid.uuid4(),
            name="Viewer",
            description="Viewer role",
            assigned_groups=["viewers"],
            feature_permissions={
                "data-products": FeatureAccessLevel.READ_ONLY,
                "data-contracts": FeatureAccessLevel.READ_ONLY,
            },
            home_sections=[],
            approval_privileges={},
        )

    # Effective permission calculation tests
    def test_get_effective_permissions_no_groups(self, manager, mock_settings_manager):
        """Test calculating permissions with no user groups."""
        mock_settings_manager.list_app_roles.return_value = []
        
        result = manager.get_user_effective_permissions([])
        
        # Should return NONE for all features
        assert all(level == FeatureAccessLevel.NONE for level in result.values())

    def test_get_effective_permissions_single_role(self, manager, mock_settings_manager, developer_role):
        """Test calculating permissions from a single matching role."""
        mock_settings_manager.list_app_roles.return_value = [developer_role]
        
        result = manager.get_user_effective_permissions(["developers"])
        
        # Should have permissions from developer role
        assert result["data-products"] == FeatureAccessLevel.READ_WRITE
        assert result["data-contracts"] == FeatureAccessLevel.READ_WRITE
        assert result["teams"] == FeatureAccessLevel.READ_ONLY

    def test_get_effective_permissions_no_matching_roles(self, manager, mock_settings_manager, developer_role):
        """Test calculating permissions when no roles match user groups."""
        mock_settings_manager.list_app_roles.return_value = [developer_role]
        
        result = manager.get_user_effective_permissions(["unknown-group"])
        
        # Should return NONE for all features
        assert all(level == FeatureAccessLevel.NONE for level in result.values())

    def test_get_effective_permissions_multiple_roles(self, manager, mock_settings_manager, developer_role, viewer_role):
        """Test merging permissions from multiple matching roles."""
        mock_settings_manager.list_app_roles.return_value = [developer_role, viewer_role]
        
        result = manager.get_user_effective_permissions(["developers", "viewers"])
        
        # Should take the highest permission level for each feature
        assert result["data-products"] == FeatureAccessLevel.READ_WRITE  # Higher of READ_WRITE and READ_ONLY
        assert result["data-contracts"] == FeatureAccessLevel.READ_WRITE

    def test_get_effective_permissions_highest_wins(self, manager, mock_settings_manager, developer_role, admin_role):
        """Test that highest permission level wins when merging."""
        mock_settings_manager.list_app_roles.return_value = [developer_role, admin_role]
        
        result = manager.get_user_effective_permissions(["developers", "admins"])
        
        # Admin permissions should win
        assert result["data-products"] == FeatureAccessLevel.ADMIN
        assert result["data-contracts"] == FeatureAccessLevel.ADMIN
        assert result["teams"] == FeatureAccessLevel.ADMIN
        assert result["settings"] == FeatureAccessLevel.ADMIN

    def test_get_effective_permissions_partial_group_match(self, manager, mock_settings_manager, developer_role):
        """Test permissions when user has some matching and some non-matching groups."""
        mock_settings_manager.list_app_roles.return_value = [developer_role]
        
        result = manager.get_user_effective_permissions(["developers", "other-group"])
        
        # Should still get developer permissions
        assert result["data-products"] == FeatureAccessLevel.READ_WRITE

    # Team role override tests
    def test_get_effective_permissions_with_team_override(self, manager, mock_settings_manager, developer_role, admin_role):
        """Test that team role override takes precedence."""
        mock_settings_manager.list_app_roles.return_value = [developer_role, admin_role]
        
        result = manager.get_user_effective_permissions(
            user_groups=["developers"],
            team_role_override="Admin"
        )
        
        # Should use admin permissions despite only having developer group
        assert result["data-products"] == FeatureAccessLevel.ADMIN
        assert result["settings"] == FeatureAccessLevel.ADMIN

    def test_get_effective_permissions_invalid_team_override(self, manager, mock_settings_manager, developer_role):
        """Test fallback when team role override doesn't exist."""
        mock_settings_manager.list_app_roles.return_value = [developer_role]
        
        result = manager.get_user_effective_permissions(
            user_groups=["developers"],
            team_role_override="NonExistentRole"
        )
        
        # Should fall back to group-based permissions
        assert result["data-products"] == FeatureAccessLevel.READ_WRITE

    # has_permission tests
    def test_has_permission_sufficient(self, manager):
        """Test permission check when user has sufficient access."""
        effective_permissions = {
            "data-products": FeatureAccessLevel.READ_WRITE,
            "data-contracts": FeatureAccessLevel.READ_ONLY,
        }
        
        # User has READ_WRITE, requires READ_ONLY
        assert manager.has_permission(
            effective_permissions,
            "data-products",
            FeatureAccessLevel.READ_ONLY
        ) is True

    def test_has_permission_exact_match(self, manager):
        """Test permission check with exact level match."""
        effective_permissions = {
            "data-products": FeatureAccessLevel.READ_WRITE,
        }
        
        assert manager.has_permission(
            effective_permissions,
            "data-products",
            FeatureAccessLevel.READ_WRITE
        ) is True

    def test_has_permission_insufficient(self, manager):
        """Test permission check when user lacks sufficient access."""
        effective_permissions = {
            "data-products": FeatureAccessLevel.READ_ONLY,
        }
        
        # User has READ_ONLY, requires READ_WRITE
        assert manager.has_permission(
            effective_permissions,
            "data-products",
            FeatureAccessLevel.READ_WRITE
        ) is False

    def test_has_permission_none_level(self, manager):
        """Test permission check when user has no access."""
        effective_permissions = {
            "data-products": FeatureAccessLevel.NONE,
        }
        
        assert manager.has_permission(
            effective_permissions,
            "data-products",
            FeatureAccessLevel.READ_ONLY
        ) is False

    def test_has_permission_missing_feature(self, manager):
        """Test permission check for feature not in permissions."""
        effective_permissions = {
            "data-products": FeatureAccessLevel.READ_WRITE,
        }
        
        # Feature not in permissions should default to NONE
        assert manager.has_permission(
            effective_permissions,
            "unknown-feature",
            FeatureAccessLevel.READ_ONLY
        ) is False

    def test_has_permission_admin_level(self, manager):
        """Test permission check with admin level."""
        effective_permissions = {
            "settings": FeatureAccessLevel.ADMIN,
        }
        
        # Admin should have all lower levels
        assert manager.has_permission(
            effective_permissions,
            "settings",
            FeatureAccessLevel.READ_ONLY
        ) is True
        assert manager.has_permission(
            effective_permissions,
            "settings",
            FeatureAccessLevel.READ_WRITE
        ) is True
        assert manager.has_permission(
            effective_permissions,
            "settings",
            FeatureAccessLevel.ADMIN
        ) is True

    # Edge cases
    def test_get_effective_permissions_none_groups(self, manager, mock_settings_manager):
        """Test handling None as user groups."""
        mock_settings_manager.list_app_roles.return_value = []
        
        result = manager.get_user_effective_permissions(None)
        
        # Should handle None gracefully and return NONE for all features
        assert all(level == FeatureAccessLevel.NONE for level in result.values())

    def test_get_effective_permissions_role_with_unknown_feature(self, manager, mock_settings_manager):
        """Test handling role with permission for unknown feature."""
        role_with_unknown = AppRole(
            id=uuid.uuid4(),
            name="TestRole",
            description="Test",
            assigned_groups=["test"],
            feature_permissions={
                "data-products": FeatureAccessLevel.READ_WRITE,
                "unknown-feature-xyz": FeatureAccessLevel.ADMIN,  # Unknown feature
            },
            home_sections=[],
            approval_privileges={},
        )
        mock_settings_manager.list_app_roles.return_value = [role_with_unknown]

        result = manager.get_user_effective_permissions(["test"])

        # Should process valid features and skip unknown ones
        assert result["data-products"] == FeatureAccessLevel.READ_WRITE
        assert "unknown-feature-xyz" not in result or result.get("unknown-feature-xyz") == FeatureAccessLevel.NONE


class TestIsUserOntosAdmin:
    """Tests for is_user_ontos_admin - the canonical Ontos-admin check.

    Ported alongside the upstream fix (databrickslabs/ontos#404/#458) that
    decoupled Ontos admin status from settings:ADMIN, which previously let any
    user with Settings write access manage MCP tokens.
    """

    @pytest.fixture
    def mock_settings_manager(self):
        return Mock()

    @pytest.fixture
    def manager(self, mock_settings_manager):
        return AuthorizationManager(settings_manager=mock_settings_manager)

    @pytest.fixture
    def is_admin_role(self):
        """A role flagged is_admin=True - the canonical admin marker."""
        return AppRole(
            id=uuid.uuid4(),
            name="Ontos Admin",
            description="Canonical admin role",
            assigned_groups=["ontos-admins"],
            feature_permissions={"settings": FeatureAccessLevel.ADMIN},
            home_sections=[],
            approval_privileges={},
            is_admin=True,
        )

    @pytest.fixture
    def settings_admin_role(self):
        """A role with settings:ADMIN but NOT is_admin=True - must NOT count as Ontos admin."""
        return AppRole(
            id=uuid.uuid4(),
            name="Settings Manager",
            description="Can administer Settings but is not an Ontos admin",
            assigned_groups=["settings-managers"],
            feature_permissions={"settings": FeatureAccessLevel.ADMIN},
            home_sections=[],
            approval_privileges={},
            is_admin=False,
        )

    def test_member_of_is_admin_role_is_admin(self, manager, mock_settings_manager, is_admin_role):
        mock_settings_manager.list_app_roles.return_value = [is_admin_role]
        assert manager.is_user_ontos_admin(["ontos-admins"]) is True

    def test_case_insensitive_group_match(self, manager, mock_settings_manager, is_admin_role):
        mock_settings_manager.list_app_roles.return_value = [is_admin_role]
        assert manager.is_user_ontos_admin(["Ontos-Admins"]) is True

    def test_settings_admin_without_is_admin_flag_is_not_ontos_admin(
        self, manager, mock_settings_manager, settings_admin_role
    ):
        """The exact regression this fix closes: settings:ADMIN != Ontos admin."""
        mock_settings_manager.list_app_roles.return_value = [settings_admin_role]
        assert manager.is_user_ontos_admin(["settings-managers"]) is False

    def test_no_groups_denied(self, manager, mock_settings_manager, is_admin_role):
        mock_settings_manager.list_app_roles.return_value = [is_admin_role]
        assert manager.is_user_ontos_admin(None) is False
        assert manager.is_user_ontos_admin([]) is False

    def test_no_matching_group_denied(self, manager, mock_settings_manager, is_admin_role):
        mock_settings_manager.list_app_roles.return_value = [is_admin_role]
        assert manager.is_user_ontos_admin(["some-other-group"]) is False

    def test_role_lookup_failure_fails_closed(self, manager, mock_settings_manager):
        mock_settings_manager.list_app_roles.side_effect = Exception("DB down")
        assert manager.is_user_ontos_admin(["ontos-admins"]) is False

