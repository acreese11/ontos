# Demo 3 (Discover) — A Data Marketplace for Business Users

> **Deck slide 18** (deck's internal label: "Demo 2 — A Data Marketplace for
> Business Users"). The **Discover** move in the lifecycle. **Slot: ~5:00** = live
> co-narration over a ~2–3 min video.
> **Narration:** Michael leads (business-user experience); Alan takes the
> architecture/ontology beat. (Per deck agenda "Demo: Discovery — Michael — 5 min".)

**Readiness: ⚠️ WORKABLE — seed (or live-subscribe) a subscription.** Marketplace is
populated (47 products incl. 🎯 Global Flight Ops); `/subscribe` + `/subscribers`
work. But **0 subscriptions are seeded** on the deployed app, and Maintain depends on
a subscriber existing. Subscribe **live on camera here** (recommended — it's the beat
anyway), using the **same consumer identity** Maintain will show receiving the alert.

**The point:** business users search for "Global Flight Ops," not `table_adsb_v2`.
Contract-backed *products*, not raw tables — and you can inspect the contract before
you trust it.

---

## Run setup (do once before recording)

| Thing | Value |
|---|---|
| Persona | **Consumer** (business-user framing) |
| Product | `🎯 Global Flight Ops` (active/published — post-seed it is) |
| Consumer identity | the **same** one Maintain (Demo 4) shows getting notified |
| Sidebar | trimmed (no MDM/Catalog Commander/Security/Compliance/Entitlements) |

1. Log in as the Consumer persona.
2. Confirm `🎯 Global Flight Ops` is active and that its product card shows trust
   signals (incl. the **last quality check** written by the Enforce demo).
3. Make sure **no** subscription exists yet for this consumer (so the live subscribe
   is clean) — or unsubscribe to reset.

## Timing budget (~5:00 slot)

| Beat | Who | Target |
|---|---|---|
| 0 · Callback to the lifecycle slide | Michael | 0:30 |
| 1 · The problem — search, don't grep table names | Michael | 0:40 |
| 2 · The product card + trust signals | Michael | 0:40 |
| 3 · Inspect before you trust (the contract/schema) | Michael→Alan | 0:50 |
| 4 · Subscribe | Michael | 0:40 |
| 5 · What a subscription *means* (architecture) | Alan | 0:40 |
| 6 · Ontology beat (one breath) | Alan | 0:30 |
| 7 · Button to Maintain | Michael | 0:20 |

> **Realism:** Discover is the **thinnest** of the four for a full 5 min — search +
> subscribe is intrinsically ~3 min. The honest way to earn 5 is **beat 3**
> (consumer-side contract inspection) and **beat 5** (what subscription buys you).
> If those land flat in rehearsal, **cut to ~3:30** and give the minute back to
> Author or Maintain — don't manufacture a fourth click. Flag for Alan/Michael.

---

## Talk track

**Beat 0 — Callback** · *[DO] flash the lifecycle slide, finger on **04 · Discover**.*
- **[SAY · Michael]** "Enforce makes the data trustworthy. Discover is how a person
  who's never met the producing team actually *finds* it — and knows, before they
  build on it, that they can rely on it."

**Beat 1 — The problem** · *[DO] open the marketplace, search "Global Flight Ops".*
- **[SAY · Michael]** "A business user — an analyst, a planner — does not know that
  the data lives in `table_adsb_v2`. They shouldn't have to. They search for the
  thing they need." **[SEE]** the search resolves to the product card.

**Beat 2 — The product card + trust signals** · *[DO] hover/point at the signals.*
- **[SEE]** **Certified · Contract version · Owning domain · Last quality check.**
- **[SAY · Michael]** "Before they touch it, they can see four things: it's
  certified, which contract version they'd be getting, which domain owns it — and
  when quality last passed." **[SAY · Alan, half-beat]** "That last-quality-check
  timestamp? That's the DQX run from the previous demo, surfaced here. The lifecycle
  is wired together — Enforce feeds Discover."

**Beat 3 — Inspect before you trust** · *[DO] open the product → contract/schema view.*
- **[SAY · Michael]** "And they don't have to take 'certified' on faith." **[DO]**
  open the product, drill into the backing contract. **[SEE]** the ODCS contract:
  schema, the output port(s), the quality expectations.
- **[SAY · Alan]** "This is the same machine-readable contract the producer authored
  and DQX enforces — the consumer reads the *exact* agreement. No 'let me find the
  right person on the data team.' The contract is the documentation."

**Beat 4 — Subscribe** · *[DO] click Subscribe.*
- **[SAY · Michael]** "They subscribe to the *product*." **[SEE]** subscription
  confirmed; subscriber count increments.
- **[SAY · Michael]** "That does two things: it locks them to this contract version,
  and it registers them for violation notifications."

**Beat 5 — What a subscription means** · *Alan.*
- **[SAY · Alan]** "Architecturally, that subscription is the thing federation breaks
  and contracts repair. It's an explicit producer → product → consumer link in Ontos.
  Version-locking means a breaking change upstream can't silently reach them. And the
  notification registration is what closes the trust loop — which you'll see fire in
  the last demo."

**Beat 6 — Ontology beat** · *Alan, one breath — do not pivot into an ontology tour.*
- **[SAY · Alan]** "And under the hood this isn't one table. Ontos composes
  `table_adsb_v2` and `table_oag_clean` into the single logical product *Global Flight
  Ops* through the ontology. Discoverability is the value; the ontology is the
  capability underneath it."

**Beat 7 — Button** · *Michael.*
- **[SAY · Michael]** "So now we have a subscribed, version-locked consumer. The
  obvious question is: what happens when the contract breaks? That's Maintain."

---

## Gotchas
- **No seeded subscriptions** — subscribe **live** (better beat) or pre-seed one.
- **Identity continuity:** use the **same consumer identity** here and in Maintain so
  the inbox that lights up in Maintain is the one that subscribed here.
- **Don't click stub products** (titles-only, for marketplace density) — they're not
  backed by real contracts.
- The `🎯` product is the demo hero — make sure it's the one you open, not a stub
  with a similar name.

## Reset between takes
Unsubscribe (`DELETE` the subscription) or re-seed (re-seeding clears all subs).
