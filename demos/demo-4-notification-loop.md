# Demo 4 — The Trust Loop Closes

> **Slide 18** · the **Enforce → Discover** join · **~2 min** · third of the
> 16–18 cluster (note: it plays *before* Demo 3 in slide order, but its
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
