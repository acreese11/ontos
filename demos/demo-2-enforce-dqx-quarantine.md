# Demo 2 (Enforce) — Bad Data Stops at the Gate

> **Deck slide 16** (deck's internal label: "Demo 3 — Bad Data Stops at the Gate");
> context slide **15** = "DQX in 2026 — What Shipped". The **Enforce** move in the
> lifecycle. **Slot: ~5:00** = live co-narration over a ~2–3 min video.
> **Narration: Alan owns it** end to end; Michael throws in one domain question
> (the [Michael Q] beat) and lets Alan tie it back. (Per Alan, 2026-06-14.)

**Readiness: ⚠️ RE-VERIFY before recording.** A prior run on `dais-aws` was clean — DQX
on `live_flights` / `safe_skies.flight_ops.adsb_v2` generated **11 rules, 6 of them the
contract's own custom quality rules**, **99.80% pass, 24 rows quarantined** to
`safe_skies.flight_ops.adsb_v2_quarantine`. **But the latest `aws-dais` run reported 100%
failure** — likely stale synthetic data vs the freshness rule + schema drift vs
`has_valid_schema`; being root-caused alongside the DQX-notebook rework
(see `plans/dais/backlog.md`). **Re-run and re-confirm these numbers before you record.**

**The point:** the contract *compiles into running checks* — bad data physically
fails to land in Gold; the pipeline doesn't crash; on-call doesn't page at 2am.

---

## Run setup (do once before recording)

| Thing | Value |
|---|---|
| Persona | Producer (you're operating the pipeline) |
| Contract | `live_flights` (active — Run-DQX is disabled on draft/schemaless) |
| Source table | `safe_skies.flight_ops.adsb_v2` (seeded with the dirty rows) |
| Quarantine | `safe_skies.flight_ops.adsb_v2_quarantine` |
| Verified result | pass=11826, fail=24, score **99.80%** |

1. Confirm `live_flights` is **active** (post-seed it is). Draft → Run-DQX disabled.
2. **Pre-run once** so the quarantine table + quality items already exist and the
   numbers are warm — then the on-camera run reproduces it without the 60–90s wait.
3. Have two tabs ready: the **contract's Quality tab**, and the **quarantine table**
   (Catalog/SQL) so you can cut to the bad rows instantly.

## Timing budget (~5:00 slot)

| Beat | Who | Target |
|---|---|---|
| 0 · Callback to the lifecycle slide | Alan | 0:30 |
| 1 · The contract carries quality rules | Alan | 0:45 |
| 2 · DQX reads ODCS natively (the differentiator) | Alan | 0:45 |
| 3 · Run DQX → results | Alan | 0:45 |
| 4 · The quarantine table + a bad row | Alan | 0:45 |
| 5 · Results write back → the trust signal | Alan | 0:30 |
| 6 · Operational impact | Michael Q → Alan | 0:40 |
| 7 · Button back to the lifecycle | Alan | 0:20 |

> **Realism:** this genuinely earns ~4:30–5:00 **because** of beats 2 and 5 (the
> "native ODCS" depth and the write-back tie-in). Strip those and it's a ~3:00
> demo. Don't pad the run itself — the narration carries the slot, not the spinner.

---

## Talk track

**Beat 0 — Callback** · *[DO] flash the "Turning Governance Into Code" slide, finger on **03 · Enforce**.*
- **[SAY · Alan]** "Author gave us a published contract. On its own, a contract is
  just a document — a promise. Enforce is where the promise gets teeth. Same spec,
  now running in the pipeline."

**Beat 1 — The contract carries quality** · *[DO] open `live_flights` → Quality tab.*
- **[SAY · Alan]** "Every published contract carries quality expectations, written
  right in the ODCS. Altitude can't be negative. The ICAO transponder code has to
  match a six-character hex pattern." **[SEE]** the `sql_expression` rules, e.g.
  `alt_baro_ft >= 0`, `icao24 rlike '^[0-9A-F]{6}$'`.
- **[SAY · Alan]** "These aren't generic null-checks. Six of these are the *domain
  team's own* rules — aviation semantics the platform team would never know to write."
- **[SAY · Alan]** "And these are the exact rules the producer authored back in Demo 1.
  Ontos compiled them straight into executable DQX checks — no separate rules file, no
  translation step. The contract *is* the ruleset."

**Beat 2 — DQX reads ODCS natively** · *[DO] point at slide 15 / DQX context if cut to it.*
- **[SAY · Alan]** "Here's the part that matters: we didn't translate this contract
  into some other rule language. **DQX reads the ODCS contract natively** — native ODCS
  support landed in DQX last year, and the contract *is* the rule source. So there's no
  second artifact to drift out of sync. The thing the producer agreed to is the exact
  thing that runs."
- **[SAY · Alan, credibility]** "And this is open source we *work on*, not just use.
  We're on the latest DQX — 0.15 — and when we hit a rough edge in that contract-reading
  path building Safe Skies, we fixed it in the open: that's **DQX PR #1191, merged June
  2nd**, shipping in the version running right here. That's the Databricks Labs flywheel —
  hit a real-world edge, fix it upstream, everyone gets it."
- *(Credibility beat — #1191 is a real merged fix to DQX's `datacontract` path; verify
  the native-ODCS "last year" date against the slide-15 "What Shipped" timeline before
  recording.)*

**Beat 3 — Run DQX → results** · *[DO] click **Run DQX** (results pre-warmed).*
- **[SAY · Alan]** "I run it against the live ADS-B feed — about twelve thousand rows."
  **[SEE]** results write back: **pass = 11,826 · fail = 24 · score 99.80%.**
- **[SAY · Alan]** "Twenty-four rows broke the contract. Now watch where they go."

**Beat 4 — The quarantine table** · *[DO] cut to `adsb_v2_quarantine`, open one row.*
- **[SEE]** the 24 quarantined rows; open one — negative altitude / malformed ICAO,
  with the **failed rule name** attached.
- **[SAY · Alan]** "This is the quarantine pattern. Valid rows flow to Gold. The 24
  bad rows route *here*, tagged with exactly which rule they broke. The main pipeline
  never crashed — it didn't even slow down. Gold stays pristine."

**Beat 5 — Write-back → trust signal** · *[DO] back to the contract; show the quality status / timestamp.*
- **[SAY · Alan]** "And the result writes back onto the contract — a pass rate and a
  timestamp. Remember that 'last quality check' — it becomes a visible trust signal
  the moment a consumer goes looking for this product. Which is the next demo."

**Beat 6 — Operational impact** · *Michael throws in the domain question; Alan answers.*
- **[Michael Q]** "So on our side — what does that actually prevent?"
- **[SAY · Alan]** "Concretely: a malformed transponder code doesn't silently corrupt
  a fleet-availability dashboard. A negative altitude doesn't quietly skew a
  maintenance trend an engineer is reading. The bad row is caught at the gate,
  isolated, and flagged — and nobody gets paged at 2am to reverse-engineer which row
  poisoned the table." *(Michael can validate with a one-liner from the operator's
  seat — but Alan owns the narration.)*

**Beat 7 — Button** · *Alan.*
- **[SAY · Alan]** "Bad data failed at the gate, not at the dashboard. So now the
  data's trustworthy — how does someone actually *find* it and know they can rely on
  it? That's Discover."

---

## Gotchas
- **Run-DQX disabled** on a contract with no schemas — use an active aviation
  contract (the guard is intentional; backend 422s otherwise).
- **Concurrent-run guard:** a second Run-DQX for the same contract while one is in
  flight returns **409**. Don't double-click on camera; wait for the first.
- The job takes ~60–90s end-to-end — **pre-run** so results are warm, or cut the wait.
- DQX pulls the contract as ODCS over HTTP; only **active/approved** contracts are
  pullable (draft → 404 by design).

## Reset between takes
Quarantine + quality items are additive; re-seed for a clean slate, or just re-run
(idempotent enough for the demo — counts stay ~stable on the same data).
