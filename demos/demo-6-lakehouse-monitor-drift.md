# Demo 6 — Drift Catches What Row-Level Checks Cannot

> **Slide 22** · the **Enforce (statistical)** beat · **~2.5 min** (the
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
