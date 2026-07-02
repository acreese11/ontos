"""
Scope-to-permission mapping for identity-path (OBO) MCP callers.

See docs/notes/MCP_AUTH_REWORK_PRD.md for the full design. Summary: MCP tools
carry a `required_scope` string (e.g. "contracts:read") originally designed
for the standalone `mcp_tokens` system. Identity-path callers (resolved via
forwarded-identity/OBO headers, see `common/authorization.py`) don't have
scopes at all — they have real Ontos permissions. This module maps the former
onto the latter so a tool's access is governed by the same `FeatureAccessLevel`
model the REST API already uses, rather than a second, parallel scope system.

Only scopes actually needed by a confirmed MCP consumer are mapped here.
Unmapped scopes return None from `scope_to_feature_requirement`, and identity
callers are denied by default for those tools (fail closed) — see PRD §4.1 for
why "analytics", "semantic", etc. are deliberately left unmapped for now
rather than given a permissive default.
"""

from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session
from fastapi import Request

from src.common.features import FeatureAccessLevel
from src.common.logging import get_logger
from src.models.users import UserInfo

logger = get_logger(__name__)


# MCP scope -> (Ontos feature_id, minimum required FeatureAccessLevel).
#
# "contracts:delete" is intentionally distinct from "contracts:write" (see
# tools/data_contracts.py's DeleteDataContractTool) so destructive operations
# require ADMIN while create/update/generate only require READ_WRITE.
SCOPE_FEATURE_MAP: Dict[str, Tuple[str, FeatureAccessLevel]] = {
    "contracts:read": ("data-contracts", FeatureAccessLevel.READ_ONLY),
    "contracts:write": ("data-contracts", FeatureAccessLevel.READ_WRITE),
    "contracts:delete": ("data-contracts", FeatureAccessLevel.ADMIN),
}


def scope_to_feature_requirement(required_scope: str) -> Optional[Tuple[str, FeatureAccessLevel]]:
    """Map an MCP tool's required_scope to an (feature_id, FeatureAccessLevel).

    Returns None when there's no mapping yet - the caller should treat this as
    "identity-path callers cannot use this tool" rather than granting access.
    """
    return SCOPE_FEATURE_MAP.get(required_scope)


async def get_effective_permissions_for_mcp(
    user_details: UserInfo,
    request: Request,
) -> Dict[str, FeatureAccessLevel]:
    """Resolve a user's effective FeatureAccessLevel map once per MCP request.

    Mirrors the precedence used by PermissionChecker/enforce_feature_permission
    in common/authorization.py (team role override > applied role override >
    group-based merge), but returns the dict instead of raising, and is called
    exactly once per request rather than once per tool. `tools/list` currently
    has ~50 candidate tools; calling the full enforce_feature_permission path
    per tool would open that many throwaway DB sessions per request via
    get_user_team_role_overrides. Resolving once and doing plain dict lookups
    (via AuthorizationManager.has_permission) per tool avoids that.
    """
    from src.common.authorization import get_user_team_role_overrides
    from src.common.manager_dependencies import get_auth_manager

    if not user_details.groups:
        logger.warning(
            "MCP identity auth: user '%s' has no groups, no permissions resolved",
            user_details.email,
        )
        return {}

    auth_manager = get_auth_manager(request)

    team_role_override = await get_user_team_role_overrides(
        user_details.email, user_details.groups or [], request
    )

    applied_role_id = None
    settings_manager = getattr(request.app.state, "settings_manager", None)
    if settings_manager:
        try:
            applied_role_id = settings_manager.get_applied_role_override_for_user(user_details.email)
        except Exception:
            applied_role_id = None

    if applied_role_id and settings_manager:
        return settings_manager.get_feature_permissions_for_role_id(applied_role_id)

    return auth_manager.get_user_effective_permissions(user_details.groups, team_role_override)


def identity_has_scope(
    effective_permissions: Dict[str, FeatureAccessLevel],
    required_scope: str,
    auth_manager,
) -> bool:
    """Check an identity-path caller's resolved permissions against a tool's scope.

    Fails closed: a scope with no entry in SCOPE_FEATURE_MAP is denied, not
    granted. Wildcard ("*") tools are intentionally never satisfiable through
    this path - admin-only/legacy tools stay reachable only via the M2M token
    fallback until explicitly mapped.
    """
    mapping = scope_to_feature_requirement(required_scope)
    if mapping is None:
        return False
    feature_id, required_level = mapping
    return auth_manager.has_permission(effective_permissions, feature_id, required_level)
