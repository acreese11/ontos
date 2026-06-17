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
2. **DQX execution as a notebook + troubleshoot the 100% `aws-dais` failure.** ⬅️ **NEXT** (the big build)
3. **Ask-Ontos draft persistence.** ❌ (after #2)
4. **Redeploy** FE + free apps. ❌ Last / as-needed for remote testing.

Deferred (revisit, do **not** start without Alan's go): show-all-quality-rules; test-check
warehouse fix; the non-talk-track docs PRs (#31 / #45 / #43 — leave open, tracked below).

---

## 🔴 Big priorities (detail)

1. **DQX execution as a NOTEBOOK** — rework the DQX Contract Validation job to run as a
   notebook so the demo audience can *see what's happening* inside (the last run took ~1 min
   with no visibility). Goal: step-by-step, observable execution (pull contract → generate DQX
   rules → apply checks → split good/bad → post results) with displayed intermediate output.
   Currently a `spark_python_task`
   (`src/backend/src/workflows/dqx_contract_validation/dqx_contract_validation.py`).
   *Open: notebook format (`.py` `# COMMAND` cells vs `.ipynb`); replace vs supplement the job.*
2. **Troubleshoot 100% DQX failure on `aws-dais`** — the last DQX run on the FE/dais workspace
   reported **100% failure**. Prime suspects (the notebook's per-check visibility will confirm):
   - **Stale synthetic data vs `position_freshness`** — seed data generated ~2026-05-28; the
     freshness rule checks `ts_utc` within 60s of now → every row fails on a later run.
   - **Schema drift vs `has_valid_schema`** — deployed `adsb_v2` drifted from the contract
     (extra cols `arr_iata`/`category`/`dep_iata`; `ts_utc`/`last_contact_utc` date→timestamp;
     `icao24`/`lat`/`lon` required→nullable) → strict schema validation fails the run.
   - Also rule-out: rule mis-targeting, auth/grants, the rule-gen path.

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
