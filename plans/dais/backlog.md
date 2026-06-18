# DAIS 2026 — Backlog & Open Threads

Single canonical tracker for in-flight work on the Safe Skies / DAIS 2026 talk.
Supersedes the former `dais-open-threads.md` + `dais-quality-backlog.md` (merged here).
Updated 2026-06-17. Legend: ✅ done · ⏳ in progress · ⚠️ blocked · ❌ not started · ❓ needs clarification.

> **Doc layout (post-reorg):** fork/demo planning lives under `plans/dais/`; fork/demo
> design + analysis notes under `docs/dais/`; demo scripts under `demos/`. Generic Ontos
> planning stays in `plans/` (e.g. `ask-ontos-discovery.md`). Don't mix the two.

---

## 🥇 Current prioritization (per Alan, 2026-06-17)

1. **Finalize the docs PRs — esp. the demo talk tracks.** ✅ **DONE.** Enforce (#22) +
   Maintain talk tracks carry the DQX-native story (0.15 + #1191 + "contract is the ruleset");
   Author got one light line. Doc reorg (#52) + tracker consolidation done. Independent review
   on record (2 blockers fixed). *Remaining non-talk-track docs PRs (#31/#45/#43) stay deferred.*
2. **DQX execution as a notebook + troubleshoot the 100% `aws-dais` failure.** ✅ **DONE +
   VALIDATED.** Reworked to a `notebook_task`; root cause fixed (errors-only scoring); Run-As
   token-exchange auth solved (no shared SP secret); multi-schema + full-load; sample failing
   records. Validated by live serverless runs on `aws-dais` (#56). Details below.
3. **Ask-Ontos draft persistence.** ✅ **DONE** (#55) — copilot draft turns persist in
   `llm_sessions`; verified end-to-end via the API (create + continue, no fork).
4. **Contract↔UC linkage (Q1, Alan 2026-06-18).** ✅ **DONE** (#57) — generator forces the full
   3-level UC `physicalName`; UC Catalog Explorer clickthrough in the contract details view.
5. **Redeploy** FE + free apps. ⏳ **IN PROGRESS** — makes all of the above live + gives the
   DQX/auth wiring its final end-to-end confirmation through the Run-DQX button.

Deferred (revisit, do **not** start without Alan's go): show-all-quality-rules; test-check
warehouse fix; the non-talk-track docs PRs (#31 / #45 / #43 — leave open, tracked below).

---

## 🔴 Big priorities (detail)

### 1. DQX execution as a NOTEBOOK — ✅ DONE + validated (#54, #56)
Reworked `dqx_contract_validation` to a **`notebook_task`** (`.py` `# COMMAND`-cell source),
self-contained via a `%pip install databricks-labs-dqx>=0.15.0` cell. Each step `display()`s
its work; the **errors-vs-warnings per-check breakdown** + **sample failing/warned records**
are the demo money shots. **Iterates every schema** in the contract in one run (dropped
`schema_index`); **full load** (dropped the validation-strategy machinery). Removed `.cache()`
(PERSIST unsupported on serverless). App-side: `jobs_manager.submit_workflow` resolves
`{{job.parameters.NAME}}` into `notebook_task.base_parameters` (unit-tested); the route submits
**one run per contract**. **Deployer fix:** `WorkspaceDeployer` imports a notebook-source `.py`
with `ImportFormat.SOURCE` (+ PYTHON, extension stripped) — `AUTO` made it a plain FILE a
`notebook_task` can't run. **Validated** by live serverless runs on `aws-dais`.

### 1b. Run-As auth — ✅ SOLVED (#56), no shared SP secret
The job authenticates to Ontos as its **own Run-As identity** by exchanging its internal token
for an app-audience OAuth token via `{workspace}/oidc/v1/token` (`audience = app oauth client
id`). Confirmed: bare runtime token → 401; exchanged → 200. Run-As principal needs only
**CAN_USE** on the app. Falls back to SP M2M from a secret. See memory
`project_databricks_app_runas_token_exchange`.

### 2. 100% `aws-dais` failure — ✅ ROOT-CAUSED (run 1077521786352682, contract `live_flights`)
The run **succeeded**; "100% failure" was the *quality result*: `pass=0 fail=11850 score=0%`.
Evidence from the quarantine table (latest run): **`with_errors=24`, `with_warnings=11850`**;
the all-rows warning is **`position_freshness`** (n=11850). Live data is ~2 days old
(`fresh_rows_within_60s = 0`). The 05-28 runs quarantined exactly **24** (the 24 genuinely
negative-altitude rows `alt_baro_positive` catches → 99.80%).
- **Real bug:** the job used `apply_checks_by_metadata_and_split` → `bad_df` for *both*
  quarantine and the score; `bad_df` includes rows flagged by **any** check (error *or*
  warning). So a `warning`-level rule (freshness) firing on stale data quarantined 100% of
  rows. Latent since 05-28 (data was fresh then); exposed by aging, **not** a code regression.
- **Fix (shipped in the notebook):** annotate with `apply_checks_by_metadata`, then drive
  **score + quarantine off errors only**; surface warnings as a separate count/breakdown.
  Restores the intended 99.80% / 24-quarantined.
- **Not the cause** (ruled out): schema-validation type drift — `strict_schema_validation=False`
  tolerates the extra cols + the `date→timestamp`/`int→bigint` differences here.
- **Demo handling (Alan):** ship the job fix; let the freshness *warning* show (static feed
  is always >60s old). The warning no longer fails the data.

---

## ✅ Shipped (merged to `dais`)

- **Quality-rules unification** — Phase 0 (DQX 0.15 pin + #1191 stub removal), 1 (check
  catalog + envelope), 2a (catalog API), 2b (catalog-driven picker), 2c (other-engine support,
  DQX default), 3 (column-level persistence), 4 (generator emits executable DQX checks).
- **Notification bridge** — product Subscribe now writes `entity_subscriptions` so the
  quality/drift trust loop notifies UI subscribers; browser-verified (+ unit tests).
- **Maintain demo** — four-beat rebalance (notify loop, drift, Lakehouse Monitoring, compliance).
- **Talk tracks finalized (#22)** — Enforce carries DQX-native (0.15 + #1191 + "contract is the
  ruleset" + Author→Enforce bridge); Maintain notes the subscribe→notify bridge is wired;
  Author got one light line; Enforce Readiness flagged RE-VERIFY (100% aws-dais failure).
- **DQX notebook + Run-As auth (#54, #56)** — demo-visible notebook, 100% failure fixed
  (errors-only scoring), Run-As token-exchange auth, multi-schema, sample failing records,
  deployer notebook-import fix. Validated on `aws-dais`.
- **Ask-Ontos draft persistence (#55)** — copilot draft turns land in `llm_sessions`.
- **Contract↔UC linkage (#57)** — full 3-level `physicalName` on AI drafts + UC Catalog
  Explorer clickthrough.
- **Doc reorg (#52)** — fork/demo planning under `plans/dais/`, design/analysis under `docs/dais/`;
  two trackers consolidated into this one (`plans/dais/backlog.md`).
- **Earlier** — live-run bug fixes (#12); Compliance/Contract Coverage (#16/#18); deck pulled +
  parsed; demos 2/3 fleshed to ~5-min slots; dev tooling (`make dev` + `peer-review-pr` skill).
- Design doc (`docs/dais/dqx-quality-rules-unification.md`) + analysis note
  (`docs/dais/quality-rules-ux-analysis.md`).

---

## 🌿 Open branches & PRs

| PR | Branch | What | Disposition |
|----|--------|------|-------------|
| ~~#52~~ | merged | doc reorg + tracker consolidation | ✅ **MERGED** 2026-06-17 |
| ~~#22~~ | merged | talk tracks (Enforce/Discover flesh + DQX-native) | ✅ **MERGED** 2026-06-17 (reviewed) |
| ~~#51~~ | closed | old quality-backlog tracker | ✅ **CLOSED** — superseded by this doc |
| #50 | `feat/quality-test-check-sample` | validate-against-sample ("Test this check") [code] | ⚠️ blocked by test-check warehouse issue — *decision needed* |
| #45 | `docs/dqx-slide-14-recommendations` | DQX slide #14 recs [docs] | Leave open (deferred); on merge, move file to `docs/dais/` |
| #43 | `docs/metadata-drift-next-priority` | metadata/tag-drift roadmap [docs] | Leave open (deferred); recommend trim to a one-line note in demo-4 |
| #31 | `docs/contract-review-workflow-analysis` | review-workflow analysis [docs] | Leave open (deferred); on merge, move file to `docs/dais/` |
| — | `agent-a75fe1fb5145ae8e8` (worktree, locked) | ask-ontos persistence WIP (+115/−8) | Finish + verify + PR (priority #3) |
| — | `upstream/llm-search-obo-token` | upstream branch, behind 132 | Not ours — **delete candidate** (verify first) |
| — | `upstream/quality-item-entity-existence` | upstream branch, behind 132 | Not ours — **delete candidate** (verify first) |

---

## 🔲 Deferred TODO (Alan: come back to these)

- [ ] **Show ALL quality rules in the Quality Rules section** — aggregate contract-level
  (`contract.qualityRules`) + table-level (`schema[*].quality`) + column-level
  (`schema[*].properties[*].quality`) into one list, each tagged with grain + column/table.
  Frontend-only, warehouse-independent.
- [ ] **Fix the test-check warehouse issue** — the synchronous warehouse query stalls when the
  serverless warehouse is cold/stopped (`_run_sql` 30s wait + poll; app principal may not
  auto-start it). Current mitigation: short timeout + "warehouse starting" message. Needs a real
  fix (async/job, warm-only acceptance, or de-scope). Gates PR #50's happy path.

---

## 🔭 Future / flagged (not committed)

- Tag/classification + description drift detection (extends the drift beat; see #43).
- SLA mapping: Lakehouse Monitoring results → contract `data_contract_sla_properties`.
- "Where this goes next" deck slide (pinned by Alan).
- Seed refactor: single-column `_qrule`s → property constraints; remove the `rcvr_cntry_code`
  sample-injection in `data_contracts_manager` read path.
- Tech-debt: 6 pre-existing failures in `test_data_products_manager.py`
  (update/publish/get_distinct_owners/create) — confirmed unrelated to recent work.

---

## ❓ Decisions needed from Alan

1. **PR #50**: merge with warm-only test-check behavior, hold until the warehouse issue is
   fixed, or de-scope the warehouse-query part for now?
2. **DQX notebook**: format (`.py` `# COMMAND` cells vs `.ipynb`) and replace-vs-supplement the
   existing `spark_python_task`?
3. **Narration ownership** (from the deck): Enforce = Alan lead + Michael ops; Discover =
   Michael lead + Alan arch. Confirm or override.
4. **Genie slide 22**: keep as ~30s static payoff or remove? (Not in the agenda lineup.)

---

## Constraints (always)

- Everything through branch + PR; **no direct commits to `dais`**.
- `gh`: `acreese11` acts on the fork (not `alan-reese_data`); switch in the same bash command.
- Local dev = local Postgres; UC tables always remote; never restart servers.
- Commits end `Co-authored-by: Isaac`; PR bodies end
  `This pull request and its description were written by Isaac.`
