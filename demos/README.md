# Safe Skies — Demo Walkthrough Scripts

Presenter scripts for the DAIS 2026 "Safe Skies" demos. One file per beat.
Each script is written for a **live dress rehearsal** against the deployed app,
so you can rehearse the clicks + narration before recording with Michael.

## The story these beats tell — the Four Moves

```
Standardize   →   Generate      →   Enforce        →   Discover
ODCS v3.1         LLM-assisted      DQX reads ODCS     Ontos marketplace
ODPS              drafting in       natively           + ontology + Genie
                  Ontos
        └──── Ontos is the substrate (Lakebase Postgres + Unity Catalog) ────┘
```

Ontos is **substrate**, not one of the moves: it's the *home* for Standardize,
the *interface* for Generate, the *consumer* of Enforce results, and the
*engine* of Discover.

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

## Readiness at a glance (from the 2026-05-29 dress rehearsal)

| Demo | Beat | State |
|------|------|-------|
| [1](demo-1-ai-contract-generation.md) | AI contract generation | ✅ ready |
| [2](demo-2-marketplace-subscribe.md) | Marketplace + subscribe | ⚠️ seed subscriptions first |
| [3](demo-3-dqx-quarantine.md) | DQX quarantine | ✅ ready |
| [4](demo-4-notification-loop.md) | Notify owner + subscribers | ❌ not built yet |
| [5](demo-5-genie-trust-signals.md) | Genie w/ trust signals | ⚠️ unverified (likely API drift) |
| [6](demo-6-lakehouse-monitor-drift.md) | Lakehouse Monitor drift | ❌ not built (cut candidate) |

See `../plans/dais-demo-readiness.md` for the full rehearsal findings.

## Timing reconciliation (vs the deck)

**Slot: 40 minutes**, co-presented (Alan + Michael), 2 min reserved for Q&A.
Demos are pre-recorded videos, narrated live, in two clusters:
- Slides 16–18 → Demos **1, 2, 4**
- Slides 21–23 → Demos **3, 6, 5**

| Demo | Slide | Allocated | Fits? |
|------|-------|-----------|-------|
| 1 contract gen | 16 | ~5:00 | ✅ if scripted tight + LLM output pinned |
| 2 marketplace | 17 | ~2:00 | ✅ |
| 4 notify loop | 18 | ~2:00 | ✅ *budget* — but ❌ not built |
| 3 DQX quarantine | 21 | ~2:00 | ✅ |
| 6 monitor drift | 22 | ~2:30 | ❌ not built (cut candidate) |
| 5 Genie | 23 | ~2:00 | ⚠️ if verified |
| **Total video** | | **~15.5 min** | **≈39% of the 40-min talk** |

**Per-demo budgets are appropriate** — each beat fits its slot (see the timing
table in each script). **The structural risk is the aggregate:** 15.5 min of
video is a high share of a 40-min co-presented slot, and live co-narration over
video tends to drift long.

**Recommended adjustment — cut Demo 6 (Monitor, 2.5 min):**
- It's the **biggest unbuilt beat** (least likely to be ready) *and* the
  **second-longest video**. Cutting drops demo video to **~13 min (~33%)** — a
  healthier ratio — and removes the largest build risk.
- Keep Slide 22 as a **static talking slide**: Michael makes the drift point
  verbally in ~20–30s. The concept lands without the video.
- This single cut fixes both the timing share *and* the readiness gap at once.

**Then prioritize the build runway on Demo 4 > Demo 5:** Demo 4 (trust loop) is
the most differentiated beat and worth building; Demo 5 (Genie) is a smaller
shape-fix on an endpoint that already exists. Both fit their 2-min budgets once
working.

