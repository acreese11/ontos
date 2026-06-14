#!/usr/bin/env bash
#
# deploy.sh — one-command deploy of Ontos to a Databricks App.
#
# Encodes the full, known-good deploy recipe so you don't re-derive the gotchas
# every time: build the frontend, sync it into the backend's static dir, bundle
# deploy, trigger the app deploy, and wait on the *new* deployment id (not a date
# prefix — that silently matches an earlier same-day deploy and smokes stale code).
#
# This is the "fast deploy" path: there is no root package.json, so the Apps
# platform never runs a slow remote `npm install && npm run build` — we ship a
# pre-built frontend instead. The slow remote build is what this avoids.
#
# Usage:
#   scripts/deploy.sh [TARGET] [PROFILE]
#
#   TARGET   databricks.yaml target (default: dais-aws)
#            one of: dev | prod | dais-aws | free-edition
#   PROFILE  databricks CLI auth profile (default: dais)
#
# Env overrides:
#   APP_NAME            app resource name           (default: ontos)
#   SKIP_FRONTEND=1     skip the yarn build + static sync (backend-only change)
#   SKIP_WAIT=1         fire the deploy, don't block on RUNNING
#   EXTRA_BUNDLE_VARS   extra `--var k=v` pairs passed to `bundle deploy`
#                       (needed for dev/prod where the warehouse lookup is "default")
#   DATABRICKS_TF_EXEC_PATH / DATABRICKS_TF_VERSION
#                       Terraform workaround for the expired-GPG-key bundle error;
#                       auto-set below if a local terraform is found.
#
# Examples:
#   scripts/deploy.sh                       # dais-aws, profile dais
#   scripts/deploy.sh free-edition fe       # validate here first
#   SKIP_FRONTEND=1 scripts/deploy.sh       # backend-only redeploy
#   EXTRA_BUNDLE_VARS="--var sql_warehouse_id=6b017b77fb6a5df9" scripts/deploy.sh dev areese
#
set -euo pipefail

TARGET="${1:-dais-aws}"
PROFILE="${2:-dais}"
APP_NAME="${APP_NAME:-ontos}"

# Resolve repo root and the bundle root (src/, where databricks.yaml lives).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_ROOT="${REPO_ROOT}/src"
cd "${BUNDLE_ROOT}"

log() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

command -v databricks >/dev/null || die "databricks CLI not found on PATH"

# Terraform workaround: `bundle deploy` downloads its own Terraform and fails with
# "openpgp: key expired" when the bundled GPG key is stale. Point it at a local
# terraform if one exists; harmless if the var is unused.
if [[ -z "${DATABRICKS_TF_EXEC_PATH:-}" ]] && command -v terraform >/dev/null; then
  export DATABRICKS_TF_EXEC_PATH="$(command -v terraform)"
  export DATABRICKS_TF_VERSION="${DATABRICKS_TF_VERSION:-1.5.7}"
fi
[[ -n "${DATABRICKS_TF_EXEC_PATH:-}" ]] && log "Using local Terraform: ${DATABRICKS_TF_EXEC_PATH} (v${DATABRICKS_TF_VERSION:-?})"

# ── 1. Build frontend + sync into backend/static ────────────────────────────
# Vite outputs to src/frontend/static (frontend/static is bundle-excluded);
# the FastAPI app serves from backend/static (FRONTEND_STATIC_DIR=./static),
# so the built assets must be copied across before the bundle uploads.
if [[ "${SKIP_FRONTEND:-0}" != "1" ]]; then
  log "Building frontend (yarn build)…"
  ( cd frontend && yarn build )
  log "Syncing built assets → backend/static"
  rm -rf backend/static
  cp -r frontend/static backend/static
else
  log "SKIP_FRONTEND=1 — reusing existing backend/static"
  [[ -f backend/static/index.html ]] || die "backend/static/index.html missing — run once without SKIP_FRONTEND"
fi

# ── 2. Capture the current deployment id (to detect the new one later) ───────
prior_deploy_id="$(databricks apps get "${APP_NAME}" -p "${PROFILE}" -o json 2>/dev/null \
  | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("active_deployment",{}).get("deployment_id",""))
except Exception: print("")' || true)"
log "Prior deployment id: ${prior_deploy_id:-<none>}"

# ── 3. Bundle deploy ────────────────────────────────────────────────────────
log "Bundle deploy → target=${TARGET} profile=${PROFILE}"
# shellcheck disable=SC2086
databricks bundle deploy --target "${TARGET}" -p "${PROFILE}" ${EXTRA_BUNDLE_VARS:-}

# Resolve the remote files path the bundle synced to; apps deploy reads from it.
files_path="$(databricks bundle summary --target "${TARGET}" -p "${PROFILE}" -o json 2>/dev/null \
  | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("workspace",{}).get("file_path",""))
except Exception: print("")')"
[[ -n "${files_path}" ]] || die "could not resolve bundle file_path from bundle summary"
log "Bundle files at: ${files_path}"

# ── 4. App deploy ───────────────────────────────────────────────────────────
log "App deploy ${APP_NAME} from ${files_path}"
databricks apps deploy "${APP_NAME}" -p "${PROFILE}" --source-code-path "${files_path}"

if [[ "${SKIP_WAIT:-0}" == "1" ]]; then
  log "SKIP_WAIT=1 — not blocking. Check: databricks apps get ${APP_NAME} -p ${PROFILE}"
  exit 0
fi

# ── 5. Wait on the NEW deployment id reaching SUCCEEDED + app RUNNING ────────
log "Waiting for a new deployment to reach SUCCEEDED + RUNNING (≈4–6 min)…"
deadline=$(( $(date +%s) + 900 ))   # 15 min cap
while :; do
  read -r dep_id dep_state app_state <<<"$(databricks apps get "${APP_NAME}" -p "${PROFILE}" -o json 2>/dev/null \
    | python3 -c 'import sys,json
d=json.load(sys.stdin)
ad=d.get("active_deployment",{})
print(ad.get("deployment_id",""), ad.get("status",{}).get("state",""), d.get("app_status",{}).get("state",""))' || echo "  ")"

  if [[ -n "${dep_id}" && "${dep_id}" != "${prior_deploy_id}" \
        && "${dep_state}" == "SUCCEEDED" && "${app_state}" == "RUNNING" ]]; then
    log "✅ Deployed. deployment_id=${dep_id} app=RUNNING"
    break
  fi
  if (( $(date +%s) > deadline )); then
    die "timed out waiting for deploy (last: id=${dep_id:-?} dep=${dep_state:-?} app=${app_state:-?})"
  fi
  printf '  … dep=%s state=%s app=%s\n' "${dep_id:-?}" "${dep_state:-?}" "${app_state:-?}"
  sleep 15
done

log "Done. App: $(databricks apps get "${APP_NAME}" -p "${PROFILE}" -o json | python3 -c 'import sys,json;print(json.load(sys.stdin).get("url",""))' 2>/dev/null || true)"
