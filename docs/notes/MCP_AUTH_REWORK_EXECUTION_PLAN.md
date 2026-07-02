# Execution Plan: Identity-Based Auth for the Ontos MCP Server

Companion to [MCP_AUTH_REWORK_PRD.md](./MCP_AUTH_REWORK_PRD.md). Each phase is sized to land as its own PR against `acreese11/ontos` (base `dais`), reviewed via the existing `peer-review-pr` skill before merge.

---

## Phase 0 — Confirm the feature-mapping gaps (no code)

**Scope narrowed after confirming the actual use case (PRD §4.0): Genie One does UC discovery natively and only pushes/pulls contracts via Ontos MCP.** `analytics:*` and `semantic:*` are deferred out of v1 entirely — they don't need feature-id decisions right now. This phase now only needs to nail down `data-contracts`:

- [x] ~~Decide feature-id homes for `semantic:*`, `sparql:query`, `analytics:*`, `costs:*`~~ — **deferred, not required for v1** (confirmed with Alan: Genie's contract drafting is contracts-only, no semantic linking, no ontos-side UC discovery).
- [ ] **[Required, critical path] Classify every `contracts:write`-scoped tool as "standard write" (create/update/generate) vs. "destructive" (delete).** Specifically: `create_draft_data_contract`, `generate_contract_from_table`, `update_data_contract` → `READ_WRITE`; `delete_data_contract` → `ADMIN`. Grep `required_scope = "contracts:write"` in `data_contracts.py` to confirm no other tools are miscategorized.
- [ ] Confirm `data-contracts` in `common/features.py` already supports `READ_WRITE` and `ADMIN` levels (it does — `READ_WRITE_ADMIN_LEVELS`, per earlier review) — no new `APP_FEATURES` entry needed for the v1 scope.
- [ ] `tags:*`, `user:read`, `search:read` — still open, but **not on the critical path** for the Genie One goal; can be resolved opportunistically or left `ADMIN`-only-by-default without blocking Phase 1/2.
- [ ] Write the final scope→(feature_id, FeatureAccessLevel) table as a plain Python dict, scoped to `data-contracts` for v1 — this becomes the single source of truth consumed in Phase 2. Tools without a mapped feature (deferred scopes) simply don't appear in `tools/list` for identity-path callers; that's the correct default, not a gap to fill.

**Output:** a finalized `data-contracts` mapping (read/write/delete → ontos `FeatureAccessLevel`), pasted into the PRD's §4.1 table. Deferred scopes documented as deferred, not left ambiguous.

---

## Phase 1 — Add forwarded-identity resolution to the MCP handler (additive, no behavior change yet)

**Files touched:**
- `src/backend/src/routes/mcp_routes.py`

**Work:**
1. Add a new dependency function, e.g. `resolve_mcp_caller(request, db, settings)`, that:
   - First tries `get_user_details_from_sdk`-style resolution (reuse the function directly rather than reimplementing — it's already a FastAPI dependency in `common/authorization.py`, so call it as a plain function or refactor the header-reading logic into a shared helper if the `Depends()` signature doesn't fit MCP's manual routing).
   - Falls back to `validate_api_key()` (existing) if no forwarded-identity headers are present and `X-API-Key` is set.
   - Returns a small union type, e.g. `MCPCaller = Union[UserInfo, MCPTokenInfo]`, so downstream code can branch on `isinstance`.
2. Wire this into `mcp_handler()`/`mcp_sse_stream()`/`mcp_delete_session()` in place of the current `validate_api_key()`-only calls — but **keep `_has_scope()` behavior unchanged for the `MCPTokenInfo` branch** so existing M2M tokens keep working exactly as today.
3. **[Revised after review] For the `UserInfo` branch, `_has_scope()` must deny by default, not stub to `True`.** The original plan ("stub it to always return `True`, Phase 2 makes it real") is a live security hole if Phase 2 doesn't land in the same PR or slips: any authenticated Databricks user who can reach the app would get **full unfiltered `tools/call` access**, including every write/delete tool, for as long as the stub is live — worse than today's system, which requires an explicitly-provisioned token with real scopes. Instead: gate the entire `UserInfo` path behind a settings flag (e.g. `MCP_IDENTITY_AUTH_ENABLED`, default `false`), and have `_has_scope()` return `False` for all `UserInfo` callers until Phase 2's real check replaces it. This makes "no enforcement yet" fail closed (zero tools visible) instead of fail open (all tools visible).

**Verification:** `test_mcp_endpoint.py` run in `--bearer-from-cli` mode against a dev server hits the new forwarded-identity path, resolves identity correctly, but `tools/list` returns an **empty list** (deny-by-default) until Phase 2 lands.

---

## Phase 2 — Real permission enforcement for the identity path

**Files touched:**
- `src/backend/src/routes/mcp_routes.py`
- Possibly a new `src/backend/src/common/mcp_permissions.py` for the mapping table + helper, to keep `mcp_routes.py` from growing a large inline dict.

**Work:**
1. Implement `scope_to_feature_requirement(required_scope: str) -> tuple[str, FeatureAccessLevel]` using the Phase 0 table (including the destructive-vs-standard-write split).
2. **[Revised after review] Do NOT call `enforce_feature_permission` once per tool.** `enforce_feature_permission` → `get_user_team_role_overrides` opens and closes its own throwaway DB session per call (`common/authorization.py`). Calling it once per registered tool during `tools/list` filtering (~48 tools currently in `tools/registry.py`) means up to 48 separate DB sessions opened per single `tools/list` request — a real connection-pool/performance risk, not just style. Instead: resolve `effective_permissions: Dict[str, FeatureAccessLevel]` **once per request** (one call to `auth_manager.get_user_effective_permissions(...)`, following the same team-role-override / applied-role-override precedence `enforce_feature_permission` already uses), then do a plain dict lookup + `ACCESS_LEVEL_ORDER` comparison per tool. Only fall back to the full `enforce_feature_permission` call path for `tools/call` (a single tool per request, where the cost is fine).
3. Update `_handle_tools_list` to filter using the once-per-request `effective_permissions` dict for `UserInfo` callers (same `-32002` semantics as before, just a cheaper backing check).
4. Update `_create_tool_context()` — no change needed, it already reads managers from `app.state`, independent of the caller type.
5. Update `_audit()` calls: `_get_username()` should return the real `user_details.email` for the identity path instead of `token_info.created_by or token_info.name`.
6. **[Added after review] Decide and implement session-identity binding**: pin each `_sessions` entry to the resolved caller identity (email for `UserInfo`, token name for `MCPTokenInfo`) at `initialize` time, and reject subsequent requests on that session id if the resolved identity differs (e.g. a session started via forwarded-identity auth later presented with an `X-API-Key` for a different principal).

**Verification:**
- Unit tests per scope prefix (per PRD §6).
- Manual test: two mock users with different `MOCK_USER_GROUPS` (per the existing local-dev mock mechanism in `authorization.py`) get different `tools/list` results.

---

## Phase 3 — Simplify the token system to "M2M only"

**Files touched:**
- `src/backend/src/models/mcp_tokens.py`
- `src/backend/src/controller/mcp_tokens_manager.py`
- `src/backend/src/routes/mcp_tokens_routes.py`
- `src/backend/alembic/versions/` (new migration)
- `src/frontend/src/views/settings-mcp.tsx`, `src/frontend/src/components/settings/mcp-tokens-settings.tsx`

**Work:**
1. Add a migration adding `is_service_principal: bool = True` (or similar) to `mcp_tokens`, defaulted `True` for all existing rows (they're all effectively M2M under the new model).
2. Update `MCPTokenCreate` model/`create_mcp_token` route to require/set this flag explicitly, with a short description in the API docstring clarifying tokens are for non-human callers only.
3. Update the Settings > MCP UI copy to reflect "service principal tokens" framing instead of general MCP access tokens, **and explicitly state that these tokens cannot be used behind a UC HTTP connection** (they only work for direct/bespoke HTTP callers — see PRD §4.2's constraint, confirmed after review that this path does not generalize to the UC-connection route).
4. No deletion of the table/manager/routes — they're still load-bearing for the M2M path, just re-scoped in purpose and documentation.

**Verification:** existing `mcp_tokens` CRUD tests still pass; new field defaults correctly on migration.

---

## Phase 4 — Update the test harness and docs

**Files touched:**
- `src/scripts/test_mcp_endpoint.py`
- `docs/notes/MCP_SERVER_PLAN.md` (mark auth section as superseded, point to the new PRD)

**Work:**
1. Add a `--forwarded-identity` test mode to the script: instead of `-t`, accept mock `X-Forwarded-Email`/`X-Forwarded-User` values for local-dev testing. **[Revised after review] Document clearly that this only tests the permission-mapping/filtering logic, not real identity verification** — `get_user_details_from_sdk` branches to a hardcoded/env-driven mock `UserInfo` in local/`MOCK_USER_DETAILS` mode *before* it ever reads forwarded headers, so the actual `X-Forwarded-Access-Token` → `current_user.me()` verification path is never exercised locally, by this script or otherwise.
2. Update the module docstring's usage examples to show both paths side by side, with the above caveat stated explicitly.
3. Add a short "Auth Model (Current)" section at the top of `MCP_SERVER_PLAN.md` linking forward to the PRD, so future readers don't implement against the stale token-only design.
4. **[Added after review] Add a manual staging-verification checklist item**: since the OBO path can't be tested locally, document the steps to verify it against a real non-local Databricks App deployment (real user, real forwarded token) before Phase 5's production cutover.

---

## Phase 5 — Reconfigure the Boeing/Genie One UC connection

**Not a code change — an operational task**, done once Phase 2 is deployed and verified:

1. Create (or update) the Unity Catalog HTTP connection for the Boeing Ontos instance with **OAuth U2M**, pointed at `https://ontos-7474644894135497.aws.databricksapps.com/api/mcp`.
2. Register/refresh the MCP Service in AI Gateway against this connection.
3. Grant `EXECUTE` on the MCP Service to the appropriate Boeing-facing group.
4. Smoke-test from Genie One chat: confirm tool calls succeed and that `tools/list` reflects the calling user's actual ontos role (not an admin-everything view, unless that user is in fact an admin). **Explicitly verify the negative case**: a Boeing user with no `data-contracts` access in ontos gets an empty/filtered `tools/list` from Genie One and cannot draft a contract — this is the confirmed intended behavior (Ontos access is required to create a contract via MCP, OBO-gated, no blanket Genie access), not a bug to fix.
5. Decommission any previously-issued human `mcp_tokens` rows tied to this integration once confirmed working (`DELETE /api/mcp-tokens/{id}`).

---

## Sequencing Notes

- Phases 1–2 are the only ones that touch runtime auth behavior; they should land close together (ideally same PR, or back-to-back) to avoid a window where identity-path callers get an unenforced stub.
- Phase 3 can land independently, any time after Phase 2, with no urgency.
- Phase 5 is gated on Phase 2 being deployed to whatever ontos instance backs the Boeing app — confirm which environment that actually is before touching the live UC connection.

## Rollback Plan

Each phase is additive until Phase 3 (which only adds a defaulted column) — reverting any single PR leaves the system in its prior working state. The highest-risk step is Phase 5 (reconfiguring a live UC connection); keep the old connection config recorded/exportable before switching auth type so it can be recreated quickly if the new path misbehaves against real Genie One traffic.
