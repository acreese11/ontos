# DAIS — Quality-rules work: backlog & open threads

Living tracker for the quality-rules unification + related work. Updated 2026-06-17.

## 🔴 Big priorities (Alan, 2026-06-17)
1. **DQX execution as a NOTEBOOK** — rework the DQX Contract Validation job to run as a
   notebook so the demo audience can *see what's happening* inside (the last run took ~1 min
   with no visibility). Goal: step-by-step, observable execution (pull contract → generate DQX
   rules → apply checks → split good/bad → post results) with printed/displayed intermediate
   output. Currently it's a `spark_python_task`
   (`src/backend/src/workflows/dqx_contract_validation/dqx_contract_validation.py`).
2. **Troubleshoot 100% DQX failure on `aws-dais`** — the last DQX run on the FE/dais workspace
   reported **100% failure**. Root-cause it (rules mis-targeting the schema? type/expr mismatch
   on the live table? the `process_text_rules`/rule-gen path? auth/grants? the seed rules' DQX
   shape vs the deployed table?). Likely related to drift on the deployed `adsb_v2`
   (the contract declares types/nullability the live table no longer matches).

## ✅ Shipped (merged to `dais`)
- Quality-rules unification: **Phase 0** (DQX 0.15 pin + #1191 stub removal), **1** (check
  catalog + envelope), **2a** (catalog API), **2b** (catalog-driven picker), **2c**
  (other-engine support, DQX default), **3** (column-level persistence), **4** (generator
  emits executable DQX checks).
- **Notification bridge**: product Subscribe now writes `entity_subscriptions` so the
  quality/drift trust loop notifies UI subscribers — browser-verified.
- Design doc (`docs/design/dqx-quality-rules-unification.md`) + analysis note.

## 🟡 Open PRs — need a review/merge decision
- **#50 — validate-against-sample ("Test this check")** [code]. Built + verified-correct
  (predicate builder 9 tests; assembled SQL; not-previewable path; UI render/fire). **Blocked**
  by the test-check warehouse issue (below) for the happy-path. *Decision: merge warm-only /
  hold / de-scope the warehouse-query part.*
- **#45** — DQX slide #14 recommendations [docs]. Ready.
- **#43** — metadata/tag-drift roadmap [docs]. Opened by a fork that over-reached; *recommend
  close or trim to a one-line note.*
- **#31** — contract-review-workflow analysis [docs]. Ready.
- **#22** — Enforce/Discover demos + open-threads tracker [docs, Stream A]. Ready.

## 🔲 TODO — deferred (Alan: come back to these)
- [ ] **Show ALL quality rules in the Quality Rules section** — aggregate contract-level
  (`contract.qualityRules`) + table-level (`schema[*].quality`) + **column-level**
  (`schema[*].properties[*].quality`) into one list, each tagged with grain + column/table.
  Frontend-only, warehouse-independent. *(deferred per Alan 2026-06-17)*
- [ ] **Fix the test-check warehouse issue** — the synchronous warehouse query stalls when the
  serverless warehouse is cold/stopped (`_run_sql` has a 30s `execute_statement` wait + poll;
  the app principal may also not auto-start it). Current mitigation: short timeout + "warehouse
  starting — try again" message. *Needs real fix (async/job, or warm-only acceptance, or
  de-scope). (Alan: needs solving, but later.)*
- [ ] **Finish ask-ontos draft persistence** — recovered WIP on branch
  `agent-a75fe1fb5145ae8e8` (+115/−8: session persistence in `contract_generator_routes.py`
  + `copilot-panel.tsx` + `llm-search-api.ts`). Needs finish + browser-verify (drafted turn
  persists + survives reload) + PR. *(Original agent died mid-task.)*
- [ ] **Redeploy FE + free apps** — both are STALE; none of this session's work (quality
  unification, notification fix, etc.) is live. Required before the demo.

## 🔭 Future / flagged (not committed)
- Tag/classification + description drift detection (extends Beat-2 drift; see #43).
- SLA mapping: Lakehouse Monitoring results → contract `data_contract_sla_properties`.
- "Where this goes next" deck slide (pinned by Alan).
- Phase 5: demo-1/demo-2 talk-track updates for the DQX-native story; seed refactor
  (single-column `_qrule`s → property constraints); remove the `rcvr_cntry_code`
  sample-injection in `data_contracts_manager` read path.
- Tech-debt: 6 pre-existing failures in `test_data_products_manager.py`
  (update/publish/get_distinct_owners/create) — confirmed unrelated to recent work.

## ❓ Decisions needed from Alan
1. **PR #50**: merge with warm-only test-check behavior, hold until the warehouse issue is
   fixed, or de-scope the warehouse-query part for now?
2. **Docs PRs**: merge #45 / #31 / #22? Close or trim #43?
3. **ask-ontos WIP**: finish next, or hold?
4. **Redeploy**: when (after which merges)?
