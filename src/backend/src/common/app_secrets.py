"""Bootstrap a Databricks Secrets scope for the Ontos app's OAuth M2M credentials.

The deployed Ontos app receives DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET
in its environment (auto-injected by Databricks Apps). Jobs spawned by Ontos
need those credentials to authenticate back into the Apps proxy — but passing
them as raw job parameters exposes them in run details, audit logs, and API
responses.

The right pattern is the ``{{secrets/scope/key}}`` substitution that Databricks
Jobs supports natively. This module:

  * Ensures a Databricks Secrets scope exists (creates it if missing).
  * Writes the SP credentials into that scope on app startup (idempotent —
    overwrites the value, which is intentional in case the SP rotates).
  * Returns a sentinel object the trigger endpoint passes through job params:
    ``{{secrets/{scope}/{key}}}`` strings rather than the raw secret.

If bootstrap fails (missing credentials, lacks permission, etc.) we log loudly
and let the trigger endpoint surface a 422 — better than silently leaking the
secret.
"""
from __future__ import annotations

from typing import Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import AclPermission

from src.common.config import Settings
from src.common.logging import get_logger

logger = get_logger(__name__)


def bootstrap_app_secrets(settings: Settings, ws: WorkspaceClient) -> bool:
    """Ensure the secrets scope + client_id/client_secret keys exist.

    Returns True on success, False if any step failed (caller logs and decides
    whether to continue starting up). Never raises.
    """
    client_id = settings.DATABRICKS_CLIENT_ID
    client_secret = settings.DATABRICKS_CLIENT_SECRET
    if not client_id or not client_secret:
        logger.info(
            "Skipping app-secrets bootstrap — DATABRICKS_CLIENT_ID/SECRET not set. "
            "This is expected on local dev unless you explicitly provision a SP."
        )
        return False

    scope = settings.APP_SECRETS_SCOPE
    id_key = settings.APP_SECRETS_CLIENT_ID_KEY
    secret_key = settings.APP_SECRETS_CLIENT_SECRET_KEY

    # 1. Create scope if it doesn't already exist.
    try:
        existing_scopes = {s.name for s in (ws.secrets.list_scopes() or [])}
    except Exception as e:
        logger.warning("Could not list secret scopes: %s", e)
        existing_scopes = set()

    if scope not in existing_scopes:
        try:
            ws.secrets.create_scope(scope=scope)
            logger.info("Created Databricks Secrets scope %r for app credentials", scope)
        except Exception as e:
            # Treat already-exists race as success; everything else is a real failure.
            msg = str(e).lower()
            if "already exists" in msg or "resource_already_exists" in msg:
                logger.info("Secrets scope %r already exists (race)", scope)
            else:
                logger.warning("Failed to create secrets scope %r: %s", scope, e)
                return False

    # 2. Write the two keys. put_secret upserts.
    try:
        ws.secrets.put_secret(scope=scope, key=id_key, string_value=client_id)
        ws.secrets.put_secret(scope=scope, key=secret_key, string_value=client_secret)
        logger.info(
            "Wrote app credentials to secrets scope %r (keys: %s, %s)",
            scope, id_key, secret_key,
        )
        return True
    except Exception as e:
        logger.warning("Failed to write app credentials to scope %r: %s", scope, e)
        return False


def client_id_ref(settings: Settings) -> str:
    """Return the {{secrets/scope/key}} placeholder for the client id."""
    return f"{{{{secrets/{settings.APP_SECRETS_SCOPE}/{settings.APP_SECRETS_CLIENT_ID_KEY}}}}}"


def client_secret_ref(settings: Settings) -> str:
    """Return the {{secrets/scope/key}} placeholder for the client secret."""
    return f"{{{{secrets/{settings.APP_SECRETS_SCOPE}/{settings.APP_SECRETS_CLIENT_SECRET_KEY}}}}}"
