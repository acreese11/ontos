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

(Genie demo cut.) See `../plans/dais/demo-readiness.md` for the full rehearsal findings.

## Timing reconciliation (vs the deck)

**Slot: 40 minutes**, co-presented (Alan + Michael), 2 min reserved for Q&A. Demos are
pre-recorded videos, narrated live, in **lifecycle order: 1 Author → 2 Enforce → 3
Discover → 4 Maintain**. (Reconcile the deck's slide order to match this flow.)

The deck agenda (slide 5 speaker notes) is the reconciled source: **4 demos, ~5 min
each**, lifecycle order. **Single narrator per demo** (the other throws in a question):
**Alan** owns Author + Enforce; **Michael** owns Discover + Maintain. A "5-min slot"
is **live narration over a ~2–3 min pre-recorded video** — narration fills the slot,
not the video runtime.

| Demo | Slot | Video | Notes |
|------|------|-------|-------|
| 1 · Author (Alan) | ~5:00 | ~5 min | The showpiece — genuinely earns 5. |
| 2 · Enforce (Alan; Michael Q) | ~5:00 | ~2–3 min | Earns ~4:30–5:00 with the native-ODCS + write-back beats. |
| 3 · Discover (Michael; Alan Q) | ~5:00 | ~2–3 min | Thinnest — realistically ~3:30; give the slack back if it drags. |
| 4 · Maintain (Michael) | ~5:00 | ~2–3 min | Coverage built; notify loop + drift ❌ not built. |
| **Total stage time** | **~20 min** | | **≈50% of the 40-min talk — demo-heavy by design (field report).** |

> The Maintain beats (Contract Coverage, notification loop, drift) are consolidated in
> [`demo-4-maintain.md`](demo-4-maintain.md). Contract Coverage is the built spine; the
> notify-loop and drift beats are unbuilt, folded into that file.

**Realism call:** the agenda's "5 each" is a round-number budget. Author earns 5;
Enforce ~4:30; Discover ~3:30; Maintain depends on what's built. Don't pad to 5 with
clicks — narration plus the cross-demo callbacks (the lifecycle slide, Enforce→Discover
trust-signal handoff) is what fills the slot honestly.

**Build runway, if pursuing the unbuilt Maintain beats:** the **notify-loop (trust loop)**
is the most differentiated and worth building first; the **drift beat** is the largest
build and the cut candidate — keep its slide (deck slide 21) as a static talking point
(~20–30s verbal) rather than a video if it isn't ready.

**Deck note (Genie cut — decided 2026-06-14):** the Genie demo is cut. The Genie slide
(deck slide 22, "Demo 5 — Trusted Genie Answers") should be **removed from the deck**.
It's already out of the agenda's demo lineup; this just makes the deck match. (Deck
edit is Alan's to make — noted here as the recommendation, not done in this repo.)
