#!/usr/bin/env bash
# Re-grant the app service principal full access to the Ontos schema after a
# Lakebase resource unbind/rebind cycle has stripped its privileges.
#
# Symptoms that mean you need this script:
#   * psycopg2.errors.InvalidSchemaName: no schema has been selected to create in
#   * The app boots into the "Service Temporarily Unavailable" maintenance page
#   * /api/connections returns 500 even though /api/health is 200
#   * SELECT has_schema_privilege('<SP-UUID>', '<schema>', 'USAGE,CREATE')
#     returns f when run as a workspace admin
#
# What strips access:
#   `databricks apps update --json` with a partial body that drops the
#   resources array. The Lakebase platform reassigns ownership of SP-created
#   objects to the workspace admin and revokes the SP's grants. Bundle deploys
#   and apps stop/start cycles are SAFE — they do not trigger this.
#
# This script does not transfer ownership back to the SP (Lakebase blocks
# ALTER ... OWNER TO for human admins). It grants explicit USAGE/CREATE/SELECT
# /INSERT/UPDATE/DELETE on the existing schema so the app can resume, and
# sets ALTER DEFAULT PRIVILEGES so new objects the SP creates get matching
# grants for the workspace admin (useful for diagnostic queries).
#
# Usage:
#   PROFILE=areese INSTANCE=ontosdb SP_UUID=<uuid> SCHEMA=app_ontos \
#     scripts/recover-lakebase-sp-access.sh
#
# Required env:
#   PROFILE    Databricks CLI profile that has admin on the workspace
#   INSTANCE   Lakebase instance name (e.g., ontosdb)
#   SP_UUID    Service principal client ID (UUID) of the app
#   SCHEMA     Ontos schema name (matches PGSCHEMA env, default app_ontos)
#
# Optional env:
#   DB         Database name on the instance (default: databricks_postgres)
#   HOST       Lakebase read_write_dns; auto-discovered if omitted
#   PG_USER    Workspace user to authenticate as; defaults to the CLI profile's user
set -euo pipefail

: "${PROFILE:?PROFILE is required}"
: "${INSTANCE:?INSTANCE is required}"
: "${SP_UUID:?SP_UUID is required}"
: "${SCHEMA:?SCHEMA is required}"
DB="${DB:-databricks_postgres}"

if [[ -z "${HOST:-}" ]]; then
  HOST=$(databricks database get-database-instance "$INSTANCE" -p "$PROFILE" -o json \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["read_write_dns"])')
fi

if [[ -z "${PG_USER:-}" ]]; then
  PG_USER=$(databricks current-user me -p "$PROFILE" -o json \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["userName"])')
fi

TOKEN=$(databricks database generate-database-credential -p "$PROFILE" \
  --json "$(printf '{"request_id":"recover-%s-%s","instance_names":["%s"]}' "$(uuidgen 2>/dev/null || date +%s)" "$$" "$INSTANCE")" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')

echo "Re-granting SP access:"
echo "  host:     $HOST"
echo "  db:       $DB"
echo "  schema:   $SCHEMA"
echo "  sp uuid:  $SP_UUID"
echo "  pg user:  $PG_USER"
echo

# Confirmation gate (#24). These GRANTs are run with a one-off generated
# credential against the live metadata DB — a typo'd SP_UUID would grant the
# wrong principal. Prompt before executing when run interactively. Skipped
# automatically when non-interactive (no TTY, e.g. bootstrap-app-permissions.sh
# delegating to this) or when ASSUME_YES=1.
if [[ -t 0 && "${ASSUME_YES:-0}" != "1" ]]; then
  echo "About to GRANT schema access on \"$SCHEMA\" to SP \"$SP_UUID\" on $HOST/$DB."
  # `|| true` so an EOF (Ctrl-D) doesn't trip `set -e` before the case runs;
  # empty/EOF falls through to the default branch and aborts cleanly.
  read -r -p "Proceed? [y/N] " _confirm || true
  case "$_confirm" in
    y|Y|yes|YES) ;;
    *) echo "Aborted."; exit 1 ;;
  esac
fi

# Grants are scoped to what the app actually needs to operate (CRUD + sequence
# usage), NOT GRANT ALL — ALL includes TRUNCATE, which a buggy job could use to
# wipe the metadata store. Schema-level USAGE+CREATE still lets the app create
# new tables (it owns the schema); these per-object grants cover tables/sequences
# it doesn't own (e.g. created before an ownership transfer). (#25)
PGPASSWORD="$TOKEN" psql \
  "host=$HOST user=$PG_USER dbname=$DB port=5432 sslmode=require" \
  -v ON_ERROR_STOP=1 -At <<SQL
GRANT USAGE, CREATE ON SCHEMA "$SCHEMA" TO "$SP_UUID";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "$SCHEMA" TO "$SP_UUID";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA "$SCHEMA" TO "$SP_UUID";
ALTER DEFAULT PRIVILEGES IN SCHEMA "$SCHEMA" GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "$SP_UUID";
ALTER DEFAULT PRIVILEGES IN SCHEMA "$SCHEMA" GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "$SP_UUID";
SELECT 'after: SP USAGE+CREATE = ' || has_schema_privilege('$SP_UUID', '$SCHEMA', 'USAGE,CREATE');
SQL

echo
echo "Done. If the app is still showing 'Service Temporarily Unavailable',"
echo "restart it:  databricks apps stop ontos -p $PROFILE && databricks apps start ontos -p $PROFILE"
