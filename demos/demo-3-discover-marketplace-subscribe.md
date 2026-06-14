# Demo 2 — A Data Marketplace for Business Users

> **Slide 17** · the **Discover** move · **~2 min** · second of the 16–18 cluster.
> Co-narrated: **Michael** = business-user experience, **Alan** = architecture.

**Readiness: ⚠️ WORKABLE — seed a subscription first.** Marketplace is populated
(47 products incl. 🎯 Global Flight Ops); `/subscribe` + `/subscribers` work.
But **0 subscriptions are seeded** on the deployed app, and Demo 4 depends on a
subscriber existing. Either subscribe live on camera here (recommended — it's
the beat anyway) or pre-seed one.

**The point:** business users search for "Global Flight Ops," not
`table_adsb_v2`. Contract-backed products, not raw tables.

## Timing budget (~2:00)
| Sub-beat | Target |
|---|---|
| Search → find the product (Michael) | 0:30 |
| Trust signals on the product card (Michael) | 0:30 |
| Subscribe — locks contract version + registers for notifications | 0:30 |
| Ontology beat: how the product is composed (Alan, brief) | 0:30 |

## Pre-flight
- Logged in as a **Consumer** persona (business-user framing).
- `🎯 Global Flight Ops` product exists and is **active/published** (it is, post-seed).
- Sidebar trimmed (no MDM/Catalog Commander/Security/Compliance/Entitlements).

## Walkthrough

1. **[SAY · Michael]** "A business user doesn't know `table_adsb_v2`. They search
   for what they need."
   **[DO]** Marketplace search → "Global Flight Ops". **[SEE]** The product card.
2. **[SEE]** Trust signals on the card: **Certified · Contract version · Owning
   domain · Last quality check.** **[SAY · Michael]** "Before they touch it, they
   can see it's certified, which contract version, who owns it, and when quality
   last passed."
3. **[DO]** Click **Subscribe**. **[SAY · Michael]** "Subscribing locks them to a
   contract version and registers them for violation notifications — that sets up
   the trust loop you'll see in a moment." **[SEE]** Subscription confirmed;
   subscriber count increments.
4. **[SAY · Alan, brief ontology beat]** "Under the hood this isn't one table —
   Ontos links `table_adsb_v2` + `table_oag_clean` into the logical product
   *Global Flight Ops* via the ontology. Discoverability is the value; the
   ontology is the supporting capability." *(Keep it to one breath — don't pivot
   into an ontology tour.)*

## Gotchas
- **No seeded subscriptions** — if your script implies a pre-existing subscriber,
  seed one before recording (or just subscribe live, which is the better beat).
- This subscription is the one Demo 4 notifies — use the **same consumer
  identity** across Demos 2 and 4 so the inbox in Demo 4 is the one you subscribed
  with here.
- Don't click into stub products (titles-only, for marketplace density) — they're
  not backed by real contracts.

## Reset between takes
Unsubscribe (`DELETE` the subscription) or re-seed. Re-seeding clears all subs.
