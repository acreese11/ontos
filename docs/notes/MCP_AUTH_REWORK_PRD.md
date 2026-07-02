# PRD: Identity-Based Auth for the Ontos MCP Server

## Status
Draft, revised after independent design review (see "Review Findings Applied" callouts throughout) — for review before implementation.

## Related
- [MCP_SERVER_PLAN.md](./MCP_SERVER_PLAN.md) — original MCP server design (token-based auth, as-built)
- Deployed instance: `https://ontos-7474644894135497.aws.databricksapps.com/api/mcp`

---

## 1. Problem Statement

The MCP server (`src/backend/src/routes/mcp_routes.py`) authenticates callers with a standalone `X-API-Key` header checked against the `mcp_tokens` table (bcrypt-hashed, admin-issued, static scopes array like `data-products:read`).

When the MCP server is fronted by a **Unity Catalog HTTP connection** (the standard way to expose it to Genie One, Genie Code, or an agent), this creates a hard conflict:

- **Databricks Apps platform auth** requires `Authorization: Bearer <databricks-oauth-token>` on every request before it reaches our FastAPI code at all (confirmed in `src/scripts/test_mcp_endpoint.py`'s own comments, and via `X-Forwarded-Access-Token`/`X-Forwarded-Email` headers already used in `common/authorization.py`).
- **Ontos's own layer** requires a *second*, different credential (`X-API-Key`) in a separate header.
- A UC HTTP connection can only inject **one** credential into **one** header slot per connection (`bearer_token` / OAuth M2M / OAuth U2M / DCR — see `docs.databricks.com/aws/en/query-federation/http`). There is no documented way to add a second static header.

The only workaround that fits within that constraint (smuggling the MCP token into the URL as a query parameter) trades one problem for a worse one: query strings routinely land in access logs, proxy logs, and UC's own audit trail (`ucHttpConnectionProxiedRequest`), so a long-lived static secret ends up persisted somewhere we don't control. Not acceptable as a permanent design.

## 2. Goals

1. Eliminate the second, bolted-on credential (`mcp_tokens` / `X-API-Key`) for the common case: a human or agent acting *as* a specific Databricks user.
2. Reuse the identity Databricks Apps already injects and validates (`X-Forwarded-Access-Token`, `X-Forwarded-Email`) — the same mechanism `get_user_details_from_sdk` already relies on for the rest of the app. **This is the preferred approach, confirmed with Alan** — OBO (on-behalf-of) identity, not a shared/service identity, is the intended model.
3. Derive MCP tool access from the **same permission model** the REST API already uses (`FeatureAccessLevel` via `AuthorizationManager.get_user_effective_permissions`), so a user's MCP capabilities are always consistent with what they can do in the UI — no separate scope system to keep in sync. **This is a hard requirement, not just a nice-to-have: a Genie One user must hold real Ontos access (`data-contracts` at `READ_WRITE` or above) to create a contract through MCP.** There is no "Genie has its own blanket access" mode — every contract-drafting call is gated by the calling human's actual Ontos permissions, confirmed as the desired behavior.
4. Preserve a path for **non-human / M2M callers** (e.g., a scheduled job or external agent with no "on behalf of" user) that still needs a standalone credential.
5. No change to the JSON-RPC surface (`initialize`, `ping`, `tools/list`, `tools/call`) or to tool implementations themselves — this is an auth-layer swap only.

## 3. Non-Goals

- Redesigning the MCP protocol handler, session management, or SSE transport.
- Changing what each tool does or its `parameters`/`required_params`.
- Building a UI for the new auth model (existing Settings > MCP page gets simplified, not replaced with something new).
- Solving UC HTTP connection's single-header limitation in general — this PRD sidesteps it by not needing a second header at all.

## 4. Proposed Design

### 4.0 Confirmed usage pattern (Boeing/Genie One) — narrows required scope

The driving use case for this rework: **Genie One drafting comprehensive data contracts**, using its own native Unity Catalog access for schema discovery, and calling Ontos MCP only to **push** (create/update contracts) or **pull** (read existing contract definitions) — not for UC discovery itself.

This materially narrows what needs to work for v1:
- `GenerateContractFromTableTool` (`tools/data_contracts.py:497-635`) already does UC schema/sample-row inspection **server-side inside ontos**, threaded through the calling user's own OBO token specifically so "UC reads, sample queries, and the LLM call all run as the user — not the app SP" (existing code comment). Genie does not need to hand ontos pre-discovered schema data, and does not need ontos's own `list_catalogs`/`get_catalog_details`/`list_schemas` (`analytics:*`) tools at all — it has native UC access for discovery.
- **Decision (confirmed with Alan): semantic/glossary linking (`search_glossary_terms`, `add_semantic_link`, `semantic:*` scope) is explicitly out of scope for v1.** Contract drafting via Genie One is contracts-only; semantic tagging may be added later as a smaller follow-up once the core push/pull workflow is proven.
- Net effect: **`analytics:*` and `semantic:*` no longer need a new `APP_FEATURES` entry to unblock this integration.** They can stay unmapped/effectively `ADMIN`-only-by-default without affecting the Genie One goal. This removes the most sensitive open mapping question from the critical path (see revised table below).
- The required scope surface for v1 is just **`contracts:read`** (`search_data_contracts`, `get_data_contract`, `list_data_contracts`, `find_assets_for_table`) and **`contracts:write`** (`generate_contract_from_table`, `create_draft_data_contract`, `update_data_contract`) — plus the delete-vs-standard-write classification from §4.1 still applies within `contracts:write` (`delete_data_contract` must not ride the same gate as `create`/`update`/`generate`).

### 4.1 Primary path: OAuth U2M + forwarded identity

Configure the UC HTTP connection pointed at the Ontos MCP endpoint with **OAuth U2M (per-user)**. Databricks then:
- Handles the OAuth consent/token flow per calling user.
- Forwards the authenticated user's identity to the app via `X-Forwarded-Access-Token` / `X-Forwarded-Email` / `X-Forwarded-User` — exactly as it does today for normal UI/API traffic.

On the Ontos side, `mcp_routes.py` stops requiring `X-API-Key` and instead:
1. Resolves `UserInfo` via the **existing** `get_user_details_from_sdk` dependency (same OBO-token-first, email-fallback logic already in `common/authorization.py`).
2. Maps each tool's `required_scope` (e.g. `"data-products:read"`, `"contracts:write"`) to an existing `(feature_id, FeatureAccessLevel)` pair and checks it via `enforce_feature_permission(...)` — the same function wizard endpoints already use for permission checks outside the `Depends()` chain.
3. Filters `tools/list` and gates `tools/call` using that result instead of the `mcp_tokens.scopes` array.

**Scope → feature mapping** (derived from current `required_scope` values across `src/backend/src/tools/*.py`):

| MCP scope prefix | Feature ID | Notes |
|---|---|---|
| `data-products:*` | `data-products` | direct match |
| `contracts:*` | `data-contracts` | direct match |
| `domains:*` | `data-domains` | direct match |
| `teams:*` | `teams` | direct match |
| `tags:*` | *(new or existing feature — confirm)* | check `APP_FEATURES` for a tags entry; add one if missing |
| `projects:*` | `projects` | direct match |
| `semantic:*`, `sparql:query` | **deferred — out of scope for v1** | confirmed with Alan: semantic/glossary linking isn't part of the Genie One contract-drafting workflow for v1 (see §4.0). Leave unmapped/`ADMIN`-only-by-default; revisit if a future integration needs it — do not fold into `data-products` implicitly. |
| `analytics:*`, `costs:*` | **deferred — out of scope for v1** | not needed for the Genie One goal (Genie does UC discovery natively, not via ontos — see §4.0). Leave unmapped/`ADMIN`-only-by-default rather than spending design effort here now. `ExecuteAnalyticsQueryTool` (`tools/unity_catalog.py`) runs arbitrary analytics queries — if these are ever exposed via MCP later, they must get a deliberate, gated `APP_FEATURES` entry, not a default-open one. |
| `user:read` | *(needs a decision)* | lowest-risk of the ungrouped scopes; still needs an explicit home rather than "no gate" |
| `search:read` | **must resolve to a concrete check, not "any Ontos access"** | there is no `FeatureAccessLevel` for "any access" — if this isn't mapped to something concrete before implementation, the path of least resistance is to leave it unchecked, which is a silent behavior change from today (a token currently must explicitly carry `search:read`) |
| `*` (wildcard/admin tools) | any | require `FeatureAccessLevel.ADMIN` on the relevant feature, or workspace-admin group |

**`read`/`write` → `FeatureAccessLevel` mapping — corrected after review:**

The original proposal ("`read` → `READ_ONLY`; `write` → `READ_WRITE`, direct match") is **not** a safe direct match. The MCP scope model and the tool registry conflate several distinct write operations (create, update, delete) under one `*:write` scope — e.g. `contracts:write` covers `data_contracts.py`'s create-draft, generate-from-table, update, *and* delete tools alike (`:200`, `:284`, `:537`, `:661`). Collapsing all of these onto `FeatureAccessLevel.READ_WRITE` means **every READ_WRITE-level UI user automatically gains MCP-callable delete access** for data products, data contracts, domains, teams, projects, and tags — something today's token model can prevent by simply not granting `*:write` scope at all, but which the new mapping cannot express at a finer grain than "read-write or not."

Before Phase 2 implementation, each `*:write`-scoped tool must be individually classified as either:
- **Standard write** (create/update) → gate at `FeatureAccessLevel.READ_WRITE`, or
- **Destructive** (delete) → gate at `FeatureAccessLevel.ADMIN`, matching how the codebase already treats other destructive/administrative actions (e.g. `entitlements`, `security-features` as `ADMIN_ONLY_LEVELS` in `common/features.py`).

This audit is now an explicit Phase 0 deliverable (see execution plan) — the mapping table above is not final until it's done.

### 4.2 Secondary path: service-principal / M2M callers

Some callers genuinely have no human to act on behalf of (a scheduled agent, an external automation). For these, keep a **slimmed-down** version of today's token system:
- Keep `mcp_tokens` table and `POST/GET/DELETE /api/mcp-tokens` (admin-only, unchanged).
- Tokens are now explicitly scoped to **service-principal use only** — documented as such — and are the exception, not the default path.
- `mcp_routes.py`'s auth dependency tries **forwarded-identity auth first**; if there's no `X-Forwarded-Access-Token`/`X-Forwarded-Email` *and* an `X-API-Key` is present, fall back to the existing `MCPTokensManager.validate_token()` check. This keeps the M2M path additive rather than a parallel primary system.
- **Important constraint, made explicit after review:** this path does **not** solve the original header-slot conflict — it *avoids* it by taking M2M traffic off the UC-HTTP-connection route entirely. M2M callers are expected to be bespoke clients holding both a Databricks token and an ontos token directly (e.g. `test_mcp_endpoint.py`'s `-b`/`-t` flags), not routed through a UC HTTP connection + AI Gateway MCP Service the way the human/Genie One path is (see Phase 5 of the execution plan). **If a future integration wants a service-principal-driven MCP connection wired the same way as the human path (UC HTTP connection → AI Gateway MCP Service), it will hit the exact same single-header-slot wall this PRD exists to solve for humans.** There is currently no proposed fix for that case — it's out of scope here and should be flagged as a known gap, not silently assumed solved. Documentation (Settings UI copy, Phase 3) must state plainly: *service-principal tokens are for direct/bespoke HTTP callers only; they cannot be used behind a UC HTTP connection.*

### 4.3 What gets removed / deprecated

- The requirement that **every** MCP caller hold an ontos-issued token.
- Any reliance on `X-API-Key` as the *only* auth signal — it becomes a fallback for the M2M case.
- The query-param workaround discussed earlier is dropped entirely; it's not needed once the header conflict disappears.

## 5. Security Considerations

- **This is not naive header trust — confirmed by tracing the actual verification path.** A concern raised in review: could a caller forge `X-Forwarded-Email`/`X-Forwarded-Access-Token` directly, bypassing Databricks Apps' proxy? Tracing `get_obo_workspace_client` (`common/workspace_client.py`) → `UsersManager.get_current_user` (`controller/users_manager.py`): the OBO path calls `obo_client.current_user.me()` **against the real Databricks workspace control plane** using the token from `X-Forwarded-Access-Token`. A forged or garbage token fails at that live SDK call, not at header inspection — this is genuine bearer-token verification, not "trust whatever's in the header." This is the strongest argument for the design and should be cited as such, not just asserted.
- **No new long-lived secret for the common case.** Per-user OAuth tokens are short-lived and managed/rotated by Databricks, not stored in a UC connection config or embedded in a URL.
- **Audit consistency.** MCP tool calls now show up under the same identity the rest of the audit log (`AuditManager`) uses (`username` = real user email, not a token's `created_by`/`name` string), which is a strict improvement for traceability.
- **Least privilege by construction — and this is the desired behavior, confirmed with Alan, not just a side effect.** A user must hold real Ontos access (e.g. `data-contracts: READ_WRITE`) to create a contract via Genie One/MCP — there is no path that lets Genie draft a contract on behalf of a user who couldn't already do so in the ontos UI. The one accepted tradeoff: a human's MCP access can no longer be scoped *narrower* than their UI role either (today an admin can hand-issue a token restricted to e.g. `data-products:read` for a human who has `READ_WRITE` in the UI). That capability goes away — accepted, since the design goal is "Ontos access ⇒ MCP access," symmetrically in both directions.
- **M2M path still needs the same scrutiny as today** — bcrypt-hashed tokens, expiration, revocation — nothing regresses there, it just becomes explicitly the exception path instead of the default.
- **Blast radius of a leaked OAuth token** is bounded by Databricks' own token lifetime/refresh semantics, versus a `mcp_tokens` row that's valid until manually revoked or its 90-day default expiry.
- **Session identity binding is currently unspecified.** `_sessions` (`mcp_routes.py`) is an in-memory dict keyed only by an opaque `secrets.token_urlsafe(32)` session id, storing `token_name` — nothing pins a session to the caller identity that created it beyond knowledge of the id itself. Decide explicitly whether a session created via the identity path should reject subsequent requests presenting the M2M fallback path (or a different user's identity) on the same session id, rather than leaving this implicit.
- **Interim risk window between Phase 1 and Phase 2 (see execution plan) must not default to open access.** If forwarded-identity callers are recognized before permission enforcement is wired up, that window must deny-by-default, not allow-by-default — see Phase 1 revision.

## 6. Testing Plan

- Extend `src/scripts/test_mcp_endpoint.py`:
  - Add a mode that supplies mock `X-Forwarded-Email`/`X-Forwarded-User` values against a local dev server. **Caveat confirmed after review: this does not exercise the real security path.** `get_user_details_from_sdk` branches on `settings.ENV`/`MOCK_USER_DETAILS` *before* it ever looks at forwarded headers — in local/mock mode it returns a hardcoded/env-var-driven `UserInfo` and never touches the `X-Forwarded-Access-Token` → `current_user.me()` verification logic at all. So this test mode only verifies the permission-mapping logic (scope→feature→tools/list filtering), not the identity-verification logic that's the actual point of this redesign.
  - Keep existing `-t`/`-b` flags working against the M2M fallback path.
- Unit tests for the new scope→feature mapping function (one test per prefix in the table above), **including explicit cases for the delete-vs-update split** (Critical Issue in §4.1 — verify a `READ_WRITE` user is rejected from delete-classified tools while an `ADMIN` user succeeds).
- Integration test: a user with `data-products: READ_ONLY` and no `data-contracts` access sees `query_data_products`/`search_data_products` in `tools/list` but not `query_data_contracts`.
- **The forwarded-identity/OBO verification path can only be genuinely tested against a real dev/staging Databricks App deployment** with `ENV` set to non-local and a real Databricks user's forwarded token — not locally, not by `test_mcp_endpoint.py` alone. Budget this as a manual staging verification step (see execution plan Phase 4), not an automated test.
- Manual verification against the real Boeing/Genie One UC connection once configured with OAuth U2M.

## 7. Rollout Plan

1. Ship the new identity-based path **behind both auth checks accepted simultaneously** (dual-support) — don't break existing `mcp_tokens` holders immediately.
2. Reconfigure the UC HTTP connection for the Boeing/Genie One integration to OAuth U2M once the new path is verified in a dev/staging ontos deployment.
3. Communicate to any existing `mcp_tokens` holders (check `list_tokens()` for what's currently issued) that human-user tokens should migrate to the OAuth U2M path; M2M tokens are unaffected.
4. After a deprecation window, restrict `mcp_tokens` issuance (`POST /api/mcp-tokens`) to a new `is_service_principal: true` flag or similar, so new human tokens can't be minted going forward.

## 8. Open Questions

- Does `tags` need a dedicated `APP_FEATURES` entry, or does it already have one under a different id? (confirm in `common/features.py`, only partially reviewed here)
- Where should `semantic`/`sparql`/`analytics`/`costs` scopes land in the feature model — new feature ids, or folded into an existing one? **These must be new, deliberate entries — not an ungated default** (see §4.1).
- Should `search:read` (global search) require any permission at all, given it already exists as a cross-cutting feature in the UI? Must resolve to a concrete `FeatureAccessLevel` check, not "any Ontos access" (no such level exists).
- Do we want the M2M fallback path gated by an explicit settings flag (`MCP_ALLOW_TOKEN_FALLBACK`) so it can be disabled entirely in environments that don't need it?
- **[Added after review] Per-tool destructive-action classification**: which `*:write`-scoped tools are actually deletes and should gate at `ADMIN` instead of `READ_WRITE`? This is now a required Phase 0 deliverable, not optional polish (see §4.1).
- **[Added after review] Performance of per-tool permission checks in `tools/list`**: `enforce_feature_permission` resolves team-role overrides via a fresh `get_db()`/`db.close()` call per invocation (`common/authorization.py`). Naively calling it once per registered tool (~48 tools currently in `tools/registry.py`) means up to 48 throwaway DB sessions per single `tools/list` request. The implementation must resolve effective permissions **once per request** and do simple dict lookups per tool — see execution plan Phase 2.
- **[Added after review] New-feature-id migration cost**: if `semantic`/`analytics`/`costs` become new `APP_FEATURES` entries, do existing `AppRole` definitions need a backfill migration so current admins/roles aren't silently dropped to `FeatureAccessLevel.NONE` for these new features?
- ~~Accepted tradeoff — no more narrower-than-UI-role MCP scoping for humans.~~ **Resolved:** confirmed accepted, and in fact the intended behavior — Ontos access is meant to gate MCP access exactly, in both directions (see §5, §2).
- **[Added after review] Was combining both credentials into a single OAuth token considered?** E.g., encoding an ontos-specific scope/claim into the M2M/U2M OAuth flow itself, so one header carries both "who" and "what," rather than splitting into forwarded-identity + separate token system. Not pursued here in favor of reusing the existing `FeatureAccessLevel` model, but worth recording as a rejected alternative rather than an unconsidered one.
- **[Added after review] Was splitting the MCP endpoint onto its own subdomain/app with platform auth disabled (relying solely on network/UC-connection-level trust) considered?** Databricks Apps' auth model is app-wide, not per-route, so this is likely infeasible as-is — but this should be confirmed and stated explicitly rather than left as a silent non-consideration.

## 9. Success Criteria

- No MCP request needs more than one credential/header to authenticate through both the Databricks Apps front door and ontos itself.
- `tools/list` output for a given user via MCP exactly matches what that user's role would allow via the REST API for the same underlying managers.
- The Boeing/Genie One MCP connection works with OAuth U2M and requires zero application-level secret to be embedded in the UC connection config.
- `mcp_tokens` usage drops to only genuine M2M/service-principal cases (verifiable via `created_by` field / audit log `TOOL_CALL` events).
