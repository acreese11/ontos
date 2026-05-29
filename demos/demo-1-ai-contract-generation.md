# Demo 1 — From Raw Data to ODCS Contract in Seconds

> **Slide 16** · the **Generate** move · **~5 min** (the longest demo; "the single
> most differentiating visual in the talk") · first of the slides 16–18 cluster.
> Co-narrated: **Michael** = business framing, **Alan** = technical mechanics.

**Readiness: ✅ READY.** `/preview` verified live on `dais-aws` (200, full
5-step pipeline, 18-col contract, model `databricks-claude-opus-4-7`). The
`temperature`-param 500 is fixed.

**The point:** AI removes the blank page; humans approve. Two datasets defuse
"you cherry-picked the table."

## Timing budget (~5:00)
| Sub-beat | Target |
|---|---|
| Setup + framing (Michael) | 0:30 |
| Table 1 (OAG schedule): profile → infer → generate → **show YAML ≥5s** | 1:45 |
| Human edit (1–2 substantive edits) + publish | 0:45 |
| Table 2 (ADS-B telemetry): profile → generate (faster, "it generalizes") | 1:30 |
| Reframe close (Alan) | 0:30 |

> ⚠️ 5 min is enough only if scripted tight. **Pin the LLM output** — cache the
> generated contract for both tables so the recording is deterministic and you
> aren't waiting on a live model call on camera (opus can take 10–30s).

## Pre-flight
- Logged in as a **Producer / domain-owner** persona.
- Two raw UC tables present and NOT yet under a published contract:
  - `safe_skies.scheduling.oag_schedule` (OAG-style schedule)
  - `safe_skies.flight_ops.adsb_v2` (ADS-B telemetry)
- Contract-generator screen reachable (the authoring wizard).

## Walkthrough

1. **[SAY · Michael]** "When a Boeing domain team gets a new dataset, the first
   question is *what's in it and can anyone trust it?* Today that's a blank YAML
   file and a week of meetings."
2. **[DO]** Open the contract authoring wizard → pick `oag_schedule`.
   **[SEE]** Table picker resolves the UC table.
3. **[SAY · Alan]** "Ontos profiles the table — sample rows, types, null/distinct,
   candidate keys — then feeds that to an LLM."
   **[DO]** Trigger generate. **[SEE]** Pipeline steps: `inspect_columns →
   sample_rows → column_stats → llm_call → parse_validate`.
4. **[SEE]** Inferred **semantic-type badges** on columns (ICAO/IATA codes,
   timestamps, PII). **[SAY · Alan]** "It recognized the ICAO codes and flagged
   PII without being told." *(This is the differentiating visual — let it land.)*
5. **[SEE]** The **ODCS v3.1 YAML** — schema, quality expectations, SLAs.
   **Hold on screen ≥5 seconds.**
6. **[DO · the human-in-the-loop beat]** Make **1–2 real edits** — e.g. tighten a
   quality rule threshold or fix a description — then **Approve / publish**.
   **[SAY · Michael]** "AI drafts; the domain owner approves. The expert still owns
   the contract."
7. **[DO]** Repeat fast on `adsb_v2`. **[SAY · Alan]** "Same flow, totally different
   shape — telemetry, not a schedule. The AI generalizes." **[SEE]** A second
   valid ODCS contract.
8. **[SAY · Alan, close]** "From raw table to a published, standards-compliant
   contract in under a minute — AI removes the blank page."

## Gotchas
- **opus-4.x rejects `temperature`** — fixed via `llm_client.chat_completion`
  (retries without it). If a *new* table errors with `BAD_REQUEST … temperature`,
  the call path didn't go through that helper.
- Identifier validation: catalog/schema/table must be plain identifiers — a bad
  name returns **422** (not a crash). Use the real `safe_skies.*` tables.
- If `/generate` (publish) 403s, it's the `data-contracts: READ_WRITE` gate —
  confirm the recording persona has write (or a transient Lakebase reconnect).

## Reset between takes
Delete the two draft contracts you published, or re-seed:
`DELETE` then `POST /api/settings/demo-data/aviation` (see `README.md`).
