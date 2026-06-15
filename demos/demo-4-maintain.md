# Demo 4 (Maintain) — Keeping Trust Honest as the Mesh Scales

> **Deck slides 20–21** (deck's internal labels: "Demo 4 — The Trust Loop Closes" +
> "Drift Catches What Row-Level Checks Cannot"). The **Maintain** move in the
> lifecycle. **Slot: ~5:00** = live narration over a video + verbal coverage of the
> not-yet-built beats.
> **Narration: Michael owns it** (deck agenda "Demo: Maintain — Michael — 5 min");
> Alan interjects on the rule mechanics / closing-the-loop ([Alan] brief beats).

Authoring and enforcing *one* contract is the easy part; maintaining trust across a
*growing* federated mesh is the real job. Three beats, in order of demo-readiness:

1. **Contract Coverage** — ✅ **BUILT + validated.** Is every table governed by exactly
   one contract? The runnable spine of the Maintain demo.
2. **Violation → Notification loop** (deck slide 20) — ❌ **NOT BUILT.** When DQX rejects
   a row, the owner + every subscriber are told. *Most differentiated; build first.* App. A.
3. **Statistical drift / Lakehouse Monitoring** (deck slide 21) — ❌ **NOT BUILT** (cut
   candidate). Drift catches what row-level checks cannot. App. B.

**The point:** trust isn't asserted once at authoring — it's *maintained* by rules that
run continuously. Coverage proves it today; the trust loop + drift are the fuller vision.

---

## Beat 1 — Contract Coverage ✅ (the runnable spine)

### What it is
A Compliance policy — **"Contract Coverage"** — that walks Unity Catalog and flags tables
with **0 contracts** (ungoverned) or **>1** (conflicting governance), scoped to a catalog:

```
MATCH (t:Object) WHERE t.type IN ['table'] AND t.catalog = 'safe_skies' AND t.schema != 'information_schema'
ASSERT t.contract_count = 1
ON_FAIL FAIL 'Table {name} has {contract_count} contract(s) (expected exactly 1)'
```

The single `ASSERT t.contract_count = 1` catches **both** failure modes: `0` (ungoverned)
and `>1` (conflicting governance).

## Run setup (do once before recording)

| Thing | Value |
|---|---|
| Persona | Producer / Governance (Compliance is a govern-stage feature) |
| Policy | **"Contract Coverage"** (id `513e36e9-…`; seeded on a fresh load) |
| Scope | catalog `safe_skies`, `information_schema` excluded |
| Verified result | 26 tables → **13 governed / 13 ungoverned = 50.0%** |

1. Confirm the **Contract Coverage** policy exists (Compliance → Policies). On an older DB,
   create it under **New Policy** with the rule above.
2. **Pre-run once** so the score + per-table results are warm; the on-camera run reproduces it.
3. Have the **failing-tables view** ready to cut to (the gap is the story).

## Timing budget (~5:00 slot)

| Beat | Who | Target |
|---|---|---|
| 0 · Frame Maintain + callback to lifecycle slide | Michael | 0:30 |
| 1 · Run the coverage policy → 50% | Michael (Alan: how the rule works) | 0:50 |
| 2 · Read the gaps (incl. `adsb_v2_raw` → Author tie-back) | Michael | 0:50 |
| 3 · The trust loop — owner + subscribers told (deck slide 20) | Michael (Alan: arch) | 1:10 |
| 4 · Drift — Lakehouse Monitoring (deck slide 21) | Michael | 0:40 |
| 5 · Button: the safety net under the whole lifecycle | Michael | 0:20 |

> **Realism:** only **Beat 1 (Coverage) is built and recordable today.** Beats 3 & 4 are
> the deck's headline Maintain beats but are **not built** — narrate them over slides
> 20–21 as the fuller vision, or build the trust loop (App. A) if there's runway. A 5-min
> slot is honest *with* the verbal trust-loop/drift coverage; **Coverage alone is ~2:30.**

## Talk track

**Beat 0 — Frame** · *[DO] flash the lifecycle slide, finger on **05 · Maintain**.*
- **[SAY · Michael]** "Authoring and enforcing one contract is the easy part. Maintaining
  trust across a *growing* mesh — that's the real job. It starts with one question: is every
  table actually governed, and is anything double-governed?"
- **[Alan, brief]** "And you can't answer that by hand across hundreds of tables — you answer
  it with a rule that runs."

**Beat 1 — Run coverage** · *[DO] Compliance → Contract Coverage → Run (pre-warmed).*
- **[SEE]** the run completes: a **coverage score + per-table pass/fail**.
- **[SAY · Michael]** "This walks the whole `safe_skies` catalog and checks every table has
  exactly one contract. We're at **50%**." **[Alan, brief]** "One rule — `contract_count = 1`
  — and it catches both failure modes: zero contracts, or two conflicting ones."

**Beat 2 — Read the gaps** · *[DO] open the failing tables.*
- **[SEE]** 13 ungoverned tables — `adsb_v2_raw`, `oag_schedule_raw`, `crew_rosters`,
  `safety_events`, `work_orders`, the `*_raw`/`*_quarantine` landing tables.
- **[SAY · Michael]** "These are ungoverned — raw landing tables, new arrivals nobody's
  contracted yet." **[Alan, tie-back]** "`adsb_v2_raw` is exactly the table we drafted a
  contract for in the first demo — this is the gap, and the Author flow is how you close it."

**Beat 3 — The trust loop** · *deck slide 20 (narrate; ❌ not built — see App. A).*
- **[SAY · Michael]** "Coverage tells you what's governed. The loop tells you when governance
  *breaks*: when DQX rejects a row against a contract, the owning team **and every subscriber**
  are notified — within seconds." **[Alan]** "That subscription from the Discover demo is the
  registration; the notification is Ontos closing the loop federation opened. The consumer
  never has to chase the producer."

**Beat 4 — Drift** · *deck slide 21 (narrate; ❌ not built — see App. B).*
- **[SAY · Michael]** "And row-level checks can't see that *yesterday's* volume was normal and
  *today's* is down 40%. That's statistical drift — Lakehouse Monitoring catches it and links
  the alert back to the contract and owning domain in Ontos."

**Beat 5 — Button** · *Michael.*
- **[SAY · Michael]** "Author, enforce, discover — with coverage, notifications, and drift
  watching the whole thing. That's operating contracts at scale, not just writing one.
  Governance is a product, not a project."

## Gotchas
- **Conflict case isn't in the seed:** after dedup cleanup there are **0** double-governed
  tables, so a live run shows the *ungoverned* (`0`) case only. To show the `>1` case on
  camera, stage it first (see "Staging the conflict case" below) or narrate the capability.
- The run walks the catalog via the warehouse — pre-run so it's warm; don't wait on camera.
- Scope is hard-coded to `safe_skies` in the rule; a different catalog needs the rule edited.

## Staging the conflict case (optional — to show both failure modes live)
The rule already flags `>1`; the seed just has no such table. To stage one:
1. Author a second draft contract whose schema references an *already-governed* table
   (e.g. one of the 13 passing tables) — via the Author flow or a quick draft.
2. Re-run Contract Coverage → that table now fails with `…has 2 contract(s) (expected exactly 1)`,
   demonstrating conflict detection alongside the ungoverned gaps.
3. Reset: delete the staged contract and re-run (or re-seed).
*(Not yet live-validated — the `>1` branch is logically covered by the same `= 1` assert,
but a real two-contract table hasn't been run on camera.)*

## Reset between takes
The coverage run is read-only + idempotent — re-run freely; the score is stable on the same
data. Re-seed only if a prior take staged a conflict contract or edited governance.

---

## Beat 2 — Violation → Notification loop ❌ NOT BUILT

> *What it would add (one line):* when DQX rejects a row against the contract, the
> contract owner **and every subscriber** receive an Ontos notification within
> seconds — the consumer never has to chase the producer. See **Appendix A** for the
> full readiness notes, build gaps, and target walkthrough.

---

## Beat 3 — Statistical drift / Lakehouse Monitoring ❌ NOT BUILT (cut candidate)

> *What it would add (one line):* DQX catches row-level violations; Lakehouse
> Monitoring catches statistical drift — "flight volume dropped 40% in the last hour"
> — and links the alert back to the contract + owning domain in Ontos. This is the
> largest remaining build and the weakest beat; **cut candidate.** See **Appendix B**
> for the full detail.

---

## Status

| Beat | Source | Build status |
|------|--------|--------------|
| 1 · Contract Coverage | (this file) | ✅ **Built + merged** — PR #16 (feature) + PR #18 (information_schema fix). Re-validated live 2026-06-15: run `2e16ed75-…` → 26 tables, 13/13, **50.0%** |
| 2 · Violation → Notification loop | demo-4 | ❌ **Not built** — most differentiated beat; worth building if there's runway |
| 3 · Statistical drift / Lakehouse Monitoring | demo-6 | ❌ **Not built — cut candidate** — largest build, weakest beat |

Coverage is the Maintain beat that actually works today. The notification loop is the
beat most worth *building* rather than cutting; drift is the cleanest thing to cut.

## Possible refinements (Beat 1 — see chat 2026-06-14, mostly deferred)
- **Conflict example:** stage one double-governed table so a live run shows both failure
  modes (currently only the ungoverned case shows). *(The one worth deciding pre-talk —
  concrete recipe now in "Staging the conflict case" above.)*
- **Exclude raw/staging** (`*_raw`, `*_quarantine`) for a "true coverage" metric — but
  keeping `adsb_v2_raw` flagged ties nicely back to the Author demo (the gap we fill with AI).
- **Severity split** via the DSL's CASE/WHEN: `>1` = error (conflict), `0` = warning
  (ungoverned). Richer, but more complexity — optional polish.

---

# Appendix A — Notification loop (demo-4, ❌ not built)

> Originally **Slide 18** · the **Enforce → Discover** join · **~2 min** · third of
> the 16–18 cluster (note: it plays *before* Demo 3 in slide order, but its
> notification fires *from* Demo 3's rejection — the videos reference each other).
> Co-narrated: **Alan** = subscriptions as a contract trust pattern, **Michael** =
> operational impact ("a consumer never has to chase the producer").

**Readiness: ❌ NOT BUILT.** The closed loop does not exist yet:
- `quality_routes` / `quality_manager` make **zero** `NotificationsManager` calls
  — a DQX/quality failure fires nothing.
- `entity_subscriptions_manager` stores subscriptions but has **no notify path**.
- 0 subscribers are seeded to notify anyway.

**This is the most differentiated beat and it needs to be built before it can be
recorded.** See "What it needs" below.

**The point:** subscriptions + notifications close the loop that federated
ownership opens. The consumer doesn't ask if data is broken — they're told.

## Timing budget (~2:00) — *once built*
| Sub-beat | Target |
|---|---|
| Recap: the subscriber from Demo 2 (Alan) | 0:20 |
| DQX rejects a row behind the scenes (callback to Demo 3) | 0:30 |
| Owner's Ontos inbox receives the notification | 0:30 |
| Subscriber's inbox receives it too — within seconds | 0:25 |
| Notification detail: offending rule + row + one-click link to contract | 0:15 |

## What it needs (build before recording)
1. **Wire quality-failure → notifications.** When DQX results write back (quality
   items with failures, or a rejection event), fire `NotificationsManager` to:
   the **contract owner** + **every subscriber** of the product whose output port
   uses that contract.
2. **Notification payload:** offending rule name, the bad row (or count), and a
   deep link to the contract.
3. **Seed a subscription** (Demo 2's consumer) so there's a subscriber inbox to
   show. Use the **same identity** as Demo 2.
4. Verify both inboxes (owner + subscriber) receive it within seconds of the
   Demo 3 rejection.

## Walkthrough (target, once built)

1. **[SAY · Alan]** "In Demo 2 a consumer subscribed to Global Flight Ops. A
   subscription is a Data Contract trust pattern — Ontos implements it directly."
2. **[DO]** Trigger / reference the DQX rejection from Demo 3 (the 24 quarantined
   rows). **[SAY · Alan]** "When DQX rejects a row against the contract…"
3. **[SEE]** The **contract owner's** Ontos inbox — a new notification: the rule
   that failed, the row, a link to the contract.
4. **[SEE]** The **subscriber's** inbox — the same notification, within seconds.
   **[SAY · Michael]** "The consumer never has to chase the producer or wonder if
   today's data is good. They're told — automatically."
5. **[DO]** Click the one-click link → lands on the contract. **[SAY · Alan]**
   "Subscriptions plus notifications close the loop that federated ownership opens."

## Presentation fallback if not built in time
- **Cut Demo 4 and fold its point into Demo 2/3 narration** ("…and every
  subscriber is notified the instant DQX rejects a row — the trust loop closes").
  Slide 18 becomes a static talking slide, not a video. Saves 2 min.
- This is the beat most worth *building* rather than cutting — it's the strongest
  "trust is engineered, not assumed" moment. Prioritize the build if there's
  runway; cut only if there isn't.

## Reset between takes
Mark notifications read / clear them; re-seed to reset subscriptions.

---

# Appendix B — Lakehouse drift (demo-6, ❌ not built, cut candidate)

> Originally **Slide 22** · the **Enforce (statistical)** beat · **~2.5 min** (the
> second-longest video) · middle of the 21–23 cluster. Co-narrated: **Michael** =
> operational framing, **Alan** = closing-the-loop callout.

**Readiness: ❌ NOT BUILT.** There is **no Lakehouse Monitor code anywhere** in
the app — no monitor-create, no drift threshold, no alert wiring. This beat is
the largest remaining build *and* the weakest beat.

**Recommendation: this is the cut candidate** (see timing note below).

**The point (if kept):** DQX catches row-level violations; Lakehouse Monitoring
catches statistical drift — "flight volume dropped 40% in the last hour" — and
links back to the contract + owning domain in Ontos.

## Timing budget (~2:30) — *if built*
| Sub-beat | Target |
|---|---|
| Why drift ≠ row-level (Michael) | 0:30 |
| The monitor on a gold flight-volume table | 0:40 |
| Volume drops 40% → alert fires (`has_no_aggr_outliers`) | 0:45 |
| Alert links back to contract + domain in Ontos (Alan) | 0:35 |

## What it would need (large build)
1. A **Lakehouse Monitor** (TimeSeries) on a gold flight-volume table in
   `safe_skies`.
2. A drift threshold + alert (Slack/email) for the "volume dropped 40% in an
   hour" scenario.
3. The alert linking back to the Ontos contract/domain (the "closing the loop"
   callout).
4. A scripted data drop to make the alert fire on camera.

This is real Databricks Lakehouse Monitoring setup + a synthetic drop scenario —
days, not hours, and none of it exists today.

## Timing / presentation recommendation (the adjustment to make)
The talk is **40 min** with **~15.5 min of pre-recorded video** (~39%). Cutting
Demo 6 is the highest-leverage adjustment because it:
- removes the **biggest unbuilt beat** (lowest chance of being ready), and
- removes the **second-longest video (2.5 min)** → demo video drops to **13 min**
  (~33% of the talk), a healthier ratio for a co-presented session.

**How to cut cleanly:** keep Slide 22 as a **static talking slide**, not a video.
Michael makes the point verbally in ~20–30s — "row-level checks miss statistical
drift; Lakehouse Monitoring catches 'volume dropped 40% in an hour' and links the
alert back to the contract in Ontos" — as a forward-looking capability. The
audience gets the concept without a video you may not be able to build or that
risks overrunning the slot.

If you keep it: it must jump the build queue ahead of Demo 4/5, which is hard to
justify given it's the least differentiated of the three.

## Walkthrough (target, only if built)
1. **[SAY · Michael]** "Row-level checks can't see that *yesterday's* volume was
   normal and *today's* is 40% down. That's drift — the harder failure."
2. **[SEE]** The Lakehouse Monitor on the gold flight-volume table.
3. **[DO]** (Scripted) volume drops 40%. **[SEE]** Alert fires:
   "Flight volume dropped 40% in the last hour."
4. **[SAY · Alan]** "And the alert links back to the contract and owning domain in
   Ontos — closing the loop is the point."

## Reset between takes
N/A until built.
