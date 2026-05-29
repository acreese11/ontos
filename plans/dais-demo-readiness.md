# DAIS Safe Skies — Demo Readiness (dress rehearsal)

**Rehearsed:** 2026-05-29 against the deployed app on `dais-aws`
(`ontos-7474644894135497.aws.databricksapps.com`, profile `dais`).
**Method:** drove each beat's backend flow via the deployed API. Seed state
healthy: 47 products, 10 active aviation contracts.

**Verdict: 2 of 6 beats are demo-ready. 1 workable with seeding. 3 are not
recordable yet — including one (D6) that is essentially unbuilt.** Half the
demo surface needs work before recording week.

## Beat-by-beat

### ✅ Demo 1 — AI contract generation — READY
`POST /api/contract-generator/preview` on `safe_skies.flight_ops.adsb_v2` →
**200**, full 5-step pipeline (inspect → sample → stats → llm → parse), 18-col
ODCS contract, model `databricks-claude-opus-4-7`. The `temperature` 500 is
fixed. Recordable today.
- *Not yet verified:* the wizard UI (badges, Q&A panel) — needs a browser pass.

### ✅ Demo 3 — DQX quarantine — READY (and now honest)
Verified earlier this session: 11 rules generated (**6 from the contract's
custom quality rules** — the Wave 1 fix), 99.80% pass, 24 rows quarantined to
`safe_skies.flight_ops.adsb_v2_quarantine`, quality items written back.
Recordable today.

### ⚠️ Demo 2 — Marketplace + Consumer subscribe — WORKABLE, needs seeding
- Marketplace populated (47 products incl. 🎯 Global Flight Ops).
- `/subscribe`, `/subscribers`, `/subscriber-count` endpoints all work (200).
- **Gap:** 0 subscribers on any product — the plan's ~5 seeded subscriptions
  are NOT present on the deployed app. The seeder doesn't appear to create them
  (or they were cleared). Demo can live-subscribe on camera (endpoint works),
  but if the script assumes a pre-existing subscription, seed it first.

### ❌ Demo 4 — Notification → owner + subscribers on rejection — NOT BUILT
The closed loop doesn't exist:
- `quality_routes.py` / `quality_manager.py` have **zero** `NotificationsManager`
  calls — a DQX/quality failure fires nothing.
- `entity_subscriptions_manager.py` stores subscriptions but has **no notify
  path** — nothing notifies subscribers on any event.
- And there are 0 subscribers seeded to notify anyway.
This is exactly plan §3b's "build the linkage if missing" — it's missing. This
is the **largest build gap** and gates the most-compelling beat (the governance
closed loop). Needs: wire quality-failure write-back → NotificationsManager →
owner + all subscribers, + seed subscriptions.

### ⚠️❌ Demo 5 — Genie with live trust signals — UNVERIFIED, likely broken
`POST /api/data-products/genie-space` (body `{"product_ids":[...]}`) → **202
accepted**, kicks off a background task. But:
- **No evidence the live Genie space was created**: no `genie_space_id`/URL
  persisted on the product, and **no completion or failure notification** (0
  notifications total on the app).
- This matches the plan's predicted risk: the `/api/2.0/genie/spaces` API
  surface likely shifted; the background task may be failing silently.
Needs: read the app `/logz` stream during a creation to capture the live API
response, fix the request/response shape, confirm `space_id` persists +
trust-signal instructions blob. Not recordable until verified.

### ❌ Demo 6 — Lakehouse Monitor drift alert — NOT BUILT
No Lakehouse Monitor code anywhere in the app (no monitor-create, no drift
threshold, no alert wiring). The only "drift" matches are schema-drift tests
and the DQX validation workflow — unrelated. This beat is vapor.
**Recommendation: cut it or replace with a lighter "drift" framing on top of
the DQX/quality signal we already have**, unless there's runway to build a real
TimeSeries monitor + alert.

## Recording-readiness summary

| Beat | State | Action before recording |
|------|-------|------------------------|
| D1 contract gen | ✅ ready | browser pass on the wizard UI |
| D3 DQX quarantine | ✅ ready | — |
| D2 marketplace+subscribe | ⚠️ workable | seed subscriptions (or live-subscribe on camera) |
| D5 Genie | ⚠️❌ unverified | log-level debug of the live Genie API call; likely a shape fix |
| D4 notify loop | ❌ not built | build quality-failure→notify(owner+subscribers) + seed subs |
| D6 monitor drift | ❌ not built | cut, or build a real monitor (largest effort) |

## Recommended sequence (2 days to code-complete)
1. **Decide D6 now** — cut or commit. It's the biggest build and the weakest
   beat; cutting frees the runway for D4/D5.
2. **D5 Genie** — verify live, fix the shape (plan est. ~1 day, mostly
   verification). High payoff, likely small fix.
3. **D4 notify loop** — build the linkage + seed subscriptions. This is the
   governance money-shot; worth the build if D6 is cut.
4. **D2** — seed subscriptions so the marketplace beat shows a populated state.
5. Browser/UI pass on D1 + D3 for the visual layer the videos actually show.

## Caveats on this rehearsal
- Verification was **backend/API-level** on the deployed app. The **UI layer**
  (badges, marketplace visuals, wizard) the videos actually show is not yet
  walked through in a browser — a separate pass with the web-devloop-tester /
  chrome-devtools is warranted once the backend beats are green.
- PAT-bearer calls resolve OBO to the SP fallback; true per-user OBO paths
  (e.g. Genie-as-user) need a browser SSO session to fully exercise.
