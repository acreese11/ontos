# Demo 5 — Trusted Genie Answers

> **Slide 23** · the **Discover / payoff** beat · **~2 min** · last of the 21–23
> cluster. Co-narrated: **Michael** = business-user value, **Alan** = trust
> signals. *One sentence* acknowledging UC Business Semantics — do **not** pivot
> into a Semantics demo.

**Readiness: ⚠️ UNVERIFIED — likely API drift.** `POST
/api/data-products/genie-space` (body `{"product_ids":[...]}`) returns **202
accepted** and kicks off a background task — but the rehearsal found **no
evidence a live space was created**: no `genie_space_id`/URL persisted on the
product, no completion/failure notification. The plan predicted the
`/api/2.0/genie/spaces` API shape may have shifted. **Verify before recording.**

**The point:** business users ask in natural language and see "Certified /
Quality Assured" — the stack below earned that trust.

## Timing budget (~2:00) — *once verified*
| Sub-beat | Target |
|---|---|
| The certified product → its Genie space (Michael) | 0:30 |
| Natural-language question + answer (Michael) | 0:45 |
| Trust signals on the answer: Certified · Contract version · Owning domain · Last quality check (Alan) | 0:30 |
| One-sentence UC Business Semantics nod (Alan) | 0:15 |

## What it needs (verify/fix before recording)
1. **Capture the live API call.** Trigger creation and read the app `/logz`
   stream (WebSocket) for the `POST /api/2.0/genie/spaces` request/response.
   Likely-to-bite: endpoint may now want `catalog_name`/`schema_name` separately,
   or `dataset_ids` instead of `tables.full_name`. Fix the request/response shape
   in `genie_client.create_genie_space` so `space_id` parses + persists.
2. **Trust-signal instructions blob.** Ensure `format_metadata_for_genie` injects
   contract version + last DQX quality score + certified status, so the cited
   sources tie back to Ontos visibly. (Optional short-text rule: "When citing
   sources, mention the certified contract from Ontos.")
3. **Confirm the space URL renders** on the product page after creation.

## Walkthrough (target, once verified)

1. **[SAY · Michael]** "The payoff: a business user opens a Genie space backed by
   the certified Global Flight Ops product. They don't need to know the
   architecture."
2. **[DO]** Open the product's Genie space → ask a natural-language question
   (e.g. "What was on-time performance by airline last week?"). **[SEE]** Genie
   answers from the contract-backed data.
3. **[SAE · Alan]** "And it shows *why* you can trust the answer — Certified,
   contract version, owning domain, last quality check — all sourced from Ontos."
   **[SEE]** Trust signals on/around the answer.
4. **[SAY · Alan, one sentence]** "It grounds on UC Business Semantics for metric
   definitions." *(Stop there — no Semantics tour.)*

## Presentation fallback if not verified in time
- The slide notes originally specified a **mocked Genie screenshot**. If the live
  space can't be made reliable, fall back to a recorded walkthrough of a
  **pre-created** space (create it once by hand, record the query), or the mock.
  2 min budget unchanged.
- This is lower build-risk than Demo 4 (the endpoint exists; it's a shape fix),
  so verifying it is likely a faster win than building Demo 4.

## Gotchas
- 202 only means *accepted* — it does **not** mean the space was created. Always
  confirm the persisted `space_id`/URL or a completion notification.
- Genie-as-the-user needs a real OBO (browser SSO) session — a PAT-bearer call
  resolves to the app SP, which may not have the same Genie access.

## Reset between takes
Delete the test Genie space in the workspace if you create throwaways during
verification; the product can hold one space reference.
