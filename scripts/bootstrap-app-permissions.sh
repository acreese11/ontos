#!/usr/bin/env bash
# One-time post-deploy bootstrap that grants the Ontos app's service principal
# every permission it needs to actually operate. Run this after the first
# `databricks bundle deploy` (which creates the app + its SP) and never again
# unless the SP UUID changes or you accidentally undo one of these grants
# (e.g. by running `databricks apps update --json` with a partial body, which
# unbinds resources and revokes Lakebase grants — see
# docs/Ontos Setup.md § "Service Principal Lost Schema Access After Apps Update").
#
# What this configures (idempotent for each step):
#
#   1. App proxy access      — grants the SP CAN_USE on the app itself so
#                              service-to-service M2M calls from background
#                              jobs (DQX validation, compliance, etc.) get
#                              past the Apps proxy (otherwise: HTTP 401).
#
#   2. Ontos role binding    — adds the SP to the workspace `admins` group
#                              (or whichever group is named in
#                              APP_ADMIN_DEFAULT_GROUPS in src/app.yaml) so
#                              the SP is recognised as an Ontos Admin and
#                              its API calls don't 403.
#
#   3. SP OAuth credentials  — mints an OAuth client secret for the SP and
#                              stashes (client_id, client_secret) in the
#                              `ontos-app` Databricks secret scope. Background
#                              jobs read these to mint M2M tokens at runtime.
#                              Creates the scope if absent.
#
#   4. UC data grants        — grants USE_CATALOG, USE_SCHEMA, SELECT, MODIFY,
#                              CREATE_TABLE, CREATE_SCHEMA on the target catalog
#                              so the SP can read source tables and write
#                              quarantine / silver / gold outputs.
#
#   5. Lakebase schema grants— GRANT USAGE/CREATE on the Ontos schema to the
#                              SP. Only needed if you accidentally unbound the
#                              database resource at some point; on a fresh
#                              deploy the app creates the schema itself as the
#                              SP and grants are unnecessary. Delegates to
#                              recover-lakebase-sp-access.sh.
#
# Usage:
#   PROFILE=dais \
#   APP_NAME=ontos \
#   CATALOG=safe_skies \
#   INSTANCE=ontosdb \
#   SCHEMA=app_ontos \
#   ADMIN_GROUP=admins \
#   SECRET_SCOPE=ontos-app \
#     scripts/bootstrap-app-permissions.sh
#
# Required env:
#   PROFILE       Databricks CLI profile with workspace-admin on the target.
#   APP_NAME      Databricks App name (the one created by bundle deploy).
#   CATALOG       Unity Catalog catalog the app reads/writes (e.g. safe_skies).
#
# Optional env:
#   INSTANCE      Lakebase instance name (default: ontosdb). Required for
#                 step 5; omit by setting SKIP_LAKEBASE=1.
#   SCHEMA        Ontos schema name in the Lakebase database (default: app_ontos).
#   ADMIN_GROUP   Workspace group that maps to Ontos Admin (default: admins).
#   SECRET_SCOPE  Secret scope name for SP credentials (default: ontos-app).
#   SKIP_LAKEBASE Set to 1 to skip step 5 (e.g. fresh deploy where SP already
#                 owns the schema).
set -euo pipefail

: "${PROFILE:?PROFILE is required}"
: "${APP_NAME:?APP_NAME is required}"
: "${CATALOG:?CATALOG is required}"

INSTANCE="${INSTANCE:-ontosdb}"
SCHEMA="${SCHEMA:-app_ontos}"
ADMIN_GROUP="${ADMIN_GROUP:-admins}"
SECRET_SCOPE="${SECRET_SCOPE:-ontos-app}"
SKIP_LAKEBASE="${SKIP_LAKEBASE:-0}"

log() { printf '\n=== %s ===\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# Discover the app SP — created by `databricks bundle deploy`, UUID stable
# across bundle redeploys but changes if the app is fully deleted + recreated.
# ---------------------------------------------------------------------------
log "Discovering app service principal"
APP_JSON=$(databricks apps get "$APP_NAME" -p "$PROFILE" -o json)
SP_UUID=$(printf '%s' "$APP_JSON" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("service_principal_client_id",""))')
SP_INTERNAL_ID=$(printf '%s' "$APP_JSON" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("service_principal_id",""))')

if [[ -z "$SP_UUID" || -z "$SP_INTERNAL_ID" ]]; then
  echo "ERROR: could not resolve app SP from 'databricks apps get $APP_NAME'." >&2
  echo "Deploy the app first with: databricks bundle deploy --target <target> -p $PROFILE" >&2
  exit 1
fi
printf '  app SP UUID:       %s\n' "$SP_UUID"
printf '  app SP internal id: %s\n' "$SP_INTERNAL_ID"

# ---------------------------------------------------------------------------
# Step 1 — App proxy access (CAN_USE for the SP).
# Without this, background jobs minting M2M tokens get HTTP 401 from the
# Apps proxy before reaching the app.
# ---------------------------------------------------------------------------
log "Step 1: grant SP CAN_USE on the app"
databricks apps update-permissions "$APP_NAME" -p "$PROFILE" --json "$(cat <<JSON
{
  "access_control_list": [
    {"service_principal_name": "$SP_UUID", "permission_level": "CAN_USE"}
  ]
}
JSON
)" > /dev/null
echo "  ok — SP has CAN_USE on $APP_NAME"

# ---------------------------------------------------------------------------
# Step 2 — Workspace group membership (Ontos role binding).
# Without this, the SP passes the Apps proxy but Ontos returns 403 because
# the SP has no group → no Ontos role → no feature permissions.
# ---------------------------------------------------------------------------
log "Step 2: add SP to workspace group '$ADMIN_GROUP'"
GROUP_ID=$(databricks api get "/api/2.0/preview/scim/v2/Groups?filter=displayName+eq+%22${ADMIN_GROUP}%22" -p "$PROFILE" -o json \
  | python3 -c 'import json,sys
d=json.load(sys.stdin)
rs=d.get("Resources",[]) or []
print(rs[0]["id"] if rs else "")')
if [[ -z "$GROUP_ID" ]]; then
  echo "ERROR: workspace group '$ADMIN_GROUP' not found. Create it first or pass a different ADMIN_GROUP." >&2
  exit 1
fi
ALREADY_MEMBER=$(databricks api get "/api/2.0/preview/scim/v2/Groups/$GROUP_ID" -p "$PROFILE" -o json \
  | python3 -c "
import json,sys
g=json.load(sys.stdin)
print('yes' if any(m.get('value')=='$SP_INTERNAL_ID' for m in g.get('members',[])) else 'no')
")
if [[ "$ALREADY_MEMBER" == "yes" ]]; then
  echo "  ok — SP already in $ADMIN_GROUP"
else
  databricks api patch "/api/2.0/preview/scim/v2/Groups/$GROUP_ID" -p "$PROFILE" --json "$(cat <<JSON
{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [{"op": "add", "path": "members", "value": [{"value": "$SP_INTERNAL_ID"}]}]
}
JSON
)" > /dev/null
  echo "  ok — added SP to $ADMIN_GROUP"
fi

# ---------------------------------------------------------------------------
# Step 3 — Secret-scope provisioning + SP OAuth credentials.
# Background jobs (DQX validation, compliance checks) need (client_id,
# client_secret) for the app's SP to mint M2M tokens at runtime. The Ontos
# app reads these from the secret scope named in APP_SECRETS_SCOPE (default
# ontos-app) and projects them into job definitions via valueFrom: "secrets/...".
# ---------------------------------------------------------------------------
log "Step 3: secret scope '$SECRET_SCOPE' + SP OAuth credentials"
SCOPE_EXISTS=$(databricks secrets list-scopes -p "$PROFILE" -o json 2>/dev/null \
  | python3 -c "import json,sys; print('yes' if any(s.get('name')=='$SECRET_SCOPE' for s in (json.load(sys.stdin) or [])) else 'no')")
if [[ "$SCOPE_EXISTS" == "no" ]]; then
  databricks secrets create-scope "$SECRET_SCOPE" -p "$PROFILE" > /dev/null
  echo "  created scope $SECRET_SCOPE"
else
  echo "  scope $SECRET_SCOPE already exists"
fi

CLIENT_ID_PRESENT=$(databricks secrets list-secrets "$SECRET_SCOPE" -p "$PROFILE" -o json 2>/dev/null \
  | python3 -c "import json,sys; print('yes' if any(s.get('key')=='client_id' for s in (json.load(sys.stdin) or [])) else 'no')")
if [[ "$CLIENT_ID_PRESENT" == "no" ]]; then
  printf '%s' "$SP_UUID" | databricks secrets put-secret "$SECRET_SCOPE" client_id -p "$PROFILE" --string-value "$SP_UUID" > /dev/null
  echo "  wrote client_id"
else
  STORED_CID=$(databricks secrets get-secret "$SECRET_SCOPE" client_id -p "$PROFILE" -o json \
    | python3 -c 'import json,sys,base64;print(base64.b64decode(json.load(sys.stdin)["value"]).decode())')
  if [[ "$STORED_CID" != "$SP_UUID" ]]; then
    warn "stored client_id ($STORED_CID) does not match current app SP ($SP_UUID). Overwriting."
    databricks secrets put-secret "$SECRET_SCOPE" client_id -p "$PROFILE" --string-value "$SP_UUID" > /dev/null
    echo "  rewrote client_id to match current SP"
  else
    echo "  client_id matches current SP"
  fi
fi

CLIENT_SECRET_PRESENT=$(databricks secrets list-secrets "$SECRET_SCOPE" -p "$PROFILE" -o json 2>/dev/null \
  | python3 -c "import json,sys; print('yes' if any(s.get('key')=='client_secret' for s in (json.load(sys.stdin) or [])) else 'no')")
if [[ "$CLIENT_SECRET_PRESENT" == "no" ]]; then
  echo "  minting a fresh OAuth client_secret for the SP…"
  NEW_SECRET=$(databricks service-principal-secrets create "$SP_INTERNAL_ID" -p "$PROFILE" -o json \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["secret"])')
  databricks secrets put-secret "$SECRET_SCOPE" client_secret -p "$PROFILE" --string-value "$NEW_SECRET" > /dev/null
  echo "  ok — client_secret stored in $SECRET_SCOPE/client_secret"
else
  echo "  client_secret already present — leaving it alone"
  echo "  (if M2M auth fails with 401, mint a fresh one:"
  echo "    databricks service-principal-secrets create $SP_INTERNAL_ID -p $PROFILE"
  echo "   then databricks secrets put-secret $SECRET_SCOPE client_secret -p $PROFILE)"
fi

# ---------------------------------------------------------------------------
# Step 4 — Unity Catalog data grants.
# Without these, the SP gets INSUFFICIENT_PRIVILEGES when reading source
# tables or writing quarantine/output tables from background jobs.
# ---------------------------------------------------------------------------
log "Step 4: UC grants on catalog '$CATALOG'"
databricks api patch "/api/2.1/unity-catalog/permissions/catalog/$CATALOG" -p "$PROFILE" --json "$(cat <<JSON
{
  "changes": [
    {"principal": "$SP_UUID", "add": ["USE_CATALOG", "USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE", "CREATE_SCHEMA"]}
  ]
}
JSON
)" > /dev/null
echo "  ok — granted USE_CATALOG, USE_SCHEMA, SELECT, MODIFY, CREATE_TABLE, CREATE_SCHEMA on $CATALOG"

# ---------------------------------------------------------------------------
# Step 5 — Lakebase schema grants (optional).
# Only needed if the SP doesn't already own / can't use the Ontos schema
# (e.g. after a resource unbind cycle reassigned ownership). On a clean
# first deploy the app creates the schema itself as the SP and this step
# is a no-op.
# ---------------------------------------------------------------------------
if [[ "$SKIP_LAKEBASE" == "1" ]]; then
  log "Step 5: skipped (SKIP_LAKEBASE=1)"
else
  log "Step 5: Lakebase schema access for SP (delegated)"
  HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PROFILE="$PROFILE" INSTANCE="$INSTANCE" SP_UUID="$SP_UUID" SCHEMA="$SCHEMA" \
    "$HERE/recover-lakebase-sp-access.sh"
fi

log "Bootstrap complete"
echo "Now restart the app so OBO + DB connections pick up the new grants:"
echo "  databricks apps stop  $APP_NAME -p $PROFILE"
echo "  databricks apps start $APP_NAME -p $PROFILE"
