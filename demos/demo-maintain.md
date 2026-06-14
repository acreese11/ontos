# Demo — Maintain (Contract Coverage + Trust Loop + Drift)

> **Lifecycle stage: Maintain** · the governance-health stage — keeping trust honest
> as the mesh scales. Authoring and enforcing *one* contract is the easy part;
> maintaining trust across a *growing* federated mesh is the real job. Three beats,
> in order of demo-readiness:
>
> 1. **Contract Coverage** — ✅ **BUILT + validated.** Is every table governed by
>    exactly one contract? This is the runnable spine of the Maintain demo.
> 2. **Violation → Notification loop** (from demo-4) — ❌ **NOT BUILT.** When DQX
>    rejects a row, the owner + every subscriber are told automatically.
> 3. **Statistical drift / Lakehouse Monitoring** (from demo-6) — ❌ **NOT BUILT**
>    (cut candidate). Drift catches what row-level checks cannot.
>
> Alan narrates throughout; Michael interjects via *[Michael Q]* prompts
> (consistent with demo-1).

---

## Beat 1 — Contract Coverage ✅ (the runnable spine)

> ~1:30–2:00 · the governance-health beat — as the mesh scales, is every table
> governed by exactly one contract? **Built + validated end-to-end (2026-06-14).**
> This is the working Maintain beat and anchors the demo.

### What it is
A Compliance policy — **"Contract Coverage"** — that walks Unity Catalog and flags tables
with **0 contracts** (ungoverned) or **>1** (conflicting governance), scoped to a catalog:

```
MATCH (t:Object) WHERE t.type IN ['table'] AND t.catalog = 'safe_skies' AND t.schema != 'information_schema'
ASSERT t.contract_count = 1
ON_FAIL FAIL 'Table {name} has {contract_count} contract(s) (expected exactly 1)'
```

### Run setup (before recording)
- The **"Contract Coverage"** policy is seeded (loads on a fresh seed). On an older DB,
  create it under **Compliance → New Policy** with the rule above.
- Scope is `safe_skies`; `information_schema` is excluded (system tables would otherwise
  flood the results and tank the score).
- **Validated live (2026-06-14):** 26 tables → **13 governed / 13 ungoverned, 50% coverage**;
  the 13 flags are real business tables (`adsb_v2_raw`, the `*_raw` / `*_quarantine` tables,
  `crew_rosters`, `safety_events`, …).
- **Conflict-case note:** after the dedup cleanup the seed has **0** double-governed tables,
  so a live run shows the *ungoverned* case only. To demo conflict detection too, either
  narrate the capability, or intentionally leave one table with two contracts.

### Talk track

**0. Frame (Maintain)**
- **[SAY]** "Authoring and enforcing one contract is the easy part. Maintaining trust across
  a *growing* mesh is the real job — and it starts with coverage: is every table governed,
  and is anything double-governed?"
- *[Michael Q]* "Across hundreds of tables, how would you even know?"

**1. Run the coverage policy**
- **[DO]** Compliance → **Contract Coverage** → Run. **[SEE]** the run completes — a coverage
  score + per-table pass/fail.
- **[SAY]** "This rule walks the whole catalog and checks every table has exactly one
  contract. We're at ~50% — and here's the gap."

**2. Read the gaps**
- **[DO]** Show the failing tables. **[SEE]** ungoverned tables — raw/landing tables, new
  arrivals nobody's contracted yet.
- **[SAY]** "These are ungoverned — raw landing tables, new arrivals. The same rule flags
  the opposite too: a table with two conflicting contracts. That's how you keep a federated
  mesh honest as it scales — not by hand, by a rule that runs."
- *[Michael Q]* "So this is the safety net under everything we just showed."

**3. Tie-back + pivot**
- **[SAY]** "Author, enforce, discover, maintain — with a coverage rule watching the whole
  thing. That's operating contracts at scale, not just writing one."

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
| 1 · Contract Coverage | (this file) | ✅ **Built + merged** — PR #16 (feature) + PR #18 (information_schema fix) + validated live 2026-06-14 |
| 2 · Violation → Notification loop | demo-4 | ❌ **Not built** — most differentiated beat; worth building if there's runway |
| 3 · Statistical drift / Lakehouse Monitoring | demo-6 | ❌ **Not built — cut candidate** — largest build, weakest beat |

Coverage is the Maintain beat that actually works today. The notification loop is the
beat most worth *building* rather than cutting; drift is the cleanest thing to cut.

## Possible refinements (Beat 1 — see chat 2026-06-14, mostly deferred)
- **Conflict example:** leave one table double-governed so a live run shows both failure
  modes (currently only the ungoverned case shows). *(The one worth deciding pre-talk.)*
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
