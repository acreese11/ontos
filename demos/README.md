# Safe Skies — Demo Walkthrough Scripts

Presenter scripts for the DAIS 2026 "Safe Skies" demos. One file per lifecycle stage.
Each script is written for a **live dress rehearsal** against the deployed app, so you
can rehearse the clicks + narration before recording with Michael.

## The story these beats tell — the lifecycle

```
Standardize  →  Author        →  Enforce         →  Discover          →  Maintain
ODCS/ODPS       AI drafts the     DQX reads ODCS     Ontos marketplace    Contract Coverage
open spec       contract in       natively in the    + subscriptions      + notify loop + drift
                Ontos             pipeline
        └──── Ontos is the substrate (Lakebase Postgres + Unity Catalog) ────┘
```

Ontos is **substrate**, not a step: the *home* for Standardize, the *interface* for
Author, the *consumer* of Enforce results, the *engine* of Discover, and the *watchdog*
for Maintain.

## Shared pre-flight (do once before a rehearsal session)

| Thing | Value |
|---|---|
| Deployed app | `https://ontos-7474644894135497.aws.databricksapps.com` (target `dais-aws`) |
| Databricks profile | `dais` (workspace `fevm-classic-stable-cy82rl`) |
| Catalog | `safe_skies` (schemas: `flight_ops`, `reference`, `scheduling`, …) |
| LLM endpoint | `databricks-claude-opus-4-7` |
| Warehouse | `27c7b0f923579921` |

1. **Auth** (the profile token expires — if any call 401s, re-run this):
   ```
   databricks auth login --profile dais
   ```
2. **Confirm the app is up** and seeded (47 products, 10 active aviation contracts):
   open the app URL, or `databricks apps get ontos -p dais`.
3. **Re-seed to a clean state** if a prior rehearsal left edits (admin only):
   ```
   TOKEN=$(databricks auth token -p dais | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
   APP=https://ontos-7474644894135497.aws.databricksapps.com
   curl -s -X DELETE -H "Authorization: Bearer $TOKEN" "$APP/api/settings/demo-data/aviation"
   curl -s -X POST   -H "Authorization: Bearer $TOKEN" "$APP/api/settings/demo-data/load-aviation" -d '{}'
   ```
   (~25s; loads domains, teams, 10 contracts, 47 products.)
4. **Persona / sidebar:** record as the **Consumer** and **Producer** personas.
   Trim MDM, Catalog Commander, Security Features, Compliance, Entitlements from
   the sidebar so the audience isn't distracted (Settings → RBAC).
5. **Caption bug:** the first ~3s of every recording shows "Synthetic flight
   telemetry — not real-world aviation data."

## Readiness at a glance

| Demo | Beat | State |
|------|------|-------|
| [1 · Author](demo-1-author-contract-generation.md) | AI contract authoring (manual + Ask Ontos) | ✅ ready |
| [2 · Enforce](demo-2-enforce-dqx-quarantine.md) | DQX quarantine | ✅ ready |
| [3 · Discover](demo-3-discover-marketplace-subscribe.md) | Marketplace + subscribe | ⚠️ seed subscriptions first |
| [4 · Maintain](demo-4-maintain.md) | Contract Coverage (+ notify loop, drift) | ✅ Coverage built + validated; notify loop ❌ not built; drift ❌ not built (cut candidate) |

(Genie demo cut.) See `../plans/dais-demo-readiness.md` for the full rehearsal findings.

## Timing reconciliation (vs the deck)

**Slot: 40 minutes**, co-presented (Alan + Michael), 2 min reserved for Q&A. Demos are
pre-recorded videos, narrated live, in **lifecycle order: 1 Author → 2 Enforce → 3
Discover → 4 Maintain**. (Reconcile the deck's slide order to match this flow.)

| Demo | Allocated | Fits? |
|------|-----------|-------|
| 1 · Author (contract authoring) | ~5:00 | ✅ if scripted tight + LLM output pinned |
| 2 · Enforce (DQX quarantine) | ~2:00 | ✅ |
| 3 · Discover (marketplace + subscribe) | ~2:00 | ✅ |
| 4 · Maintain (Coverage spine) | ~2:00 | ✅ Coverage built; notify loop + drift ❌ not built |
| **Total video** | **~11 min** | **≈28% of the 40-min talk** |

> The Maintain beats (Contract Coverage, notification loop, drift) are consolidated in
> [`demo-4-maintain.md`](demo-4-maintain.md). Contract Coverage is the built spine; the
> notify-loop and drift beats are unbuilt, folded into that file.

**Per-demo budgets are appropriate** — each fits its slot. With Genie cut and only the
built Maintain spine, demo video is **~11 min (~28%)** of the 40-min co-presented slot —
a healthy ratio with room for live co-narration drift.

**Build runway, if pursuing the unbuilt Maintain beats:** the **notify-loop (trust loop)**
is the most differentiated and worth building first; the **drift beat** is the largest
build and the cut candidate — keep its slide as a static talking point (~20–30s verbal)
rather than a video if it isn't ready.
