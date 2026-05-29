# Demo 3 — Bad Data Stops at the Gate

> **Slide 21** · the **Enforce** move · **~2 min** · first of the slides 21–23
> cluster. Co-narrated: **Alan** = technical pattern, **Michael** = operational
> impact in domain terms.

**Readiness: ✅ READY — and now honest.** Verified live on `dais-aws`:
DQX on `live_flights` / `safe_skies.flight_ops.adsb_v2` generated **11 rules, 6
of them the contract's custom quality rules** (the fix that made the "our domain
rules caught it" story true), **99.80% pass, 24 rows quarantined** to
`safe_skies.flight_ops.adsb_v2_quarantine`.

**The point:** quality checks at ingestion — bad data physically fails to land
in Gold; the pipeline doesn't crash; on-call doesn't page at 2am.

## Timing budget (~2:00)
| Sub-beat | Target |
|---|---|
| Show the contract's quality rules / the rule code (Alan) | 0:30 |
| Run DQX → results (pass/fail counts) (Alan) | 0:40 |
| The bad row + the quarantine table (Alan) | 0:30 |
| Operational impact (Michael) | 0:20 |

## Pre-flight
- `live_flights` contract is **active** (it is, post-seed) — the Run-DQX button is
  disabled on schemaless/draft contracts, so use an active aviation contract.
- The seeded ADS-B data includes the intentional dirty rows (negative altitude,
  malformed ICAO) that the custom rules catch.
- (Optional) pre-run once so the quarantine table + quality items already exist;
  then the on-camera run reproduces it.

## Walkthrough

1. **[SAY · Alan]** "Every published contract carries quality expectations. Here
   are the rules on the live-flights contract — altitude can't be negative, ICAO
   must match the hex pattern." **[DO]** Show the contract's quality rules (the
   `sql_expression` checks). **[SEE]** The custom rules, e.g. `alt_baro_ft >= 0`,
   `icao24 rlike '^[0-9A-F]{6}$'`.
2. **[DO]** Click **Run DQX**. **[SEE]** The job runs; results write back:
   **pass=11826, fail=24, score 99.80%.** **[SAY · Alan]** "DQX reads the ODCS
   contract natively — no separate rule language — and 6 of these are the domain
   team's own custom rules."
3. **[SEE]** The **quarantine table** `adsb_v2_quarantine` with the 24 bad rows —
   negative altitude / malformed ICAO. **[SAY · Alan]** "The bad rows route to
   quarantine. The main pipeline keeps running; the Gold layer stays pristine."
4. **[SAY · Michael]** "In domain terms: a malformed transponder code doesn't
   silently corrupt a fleet dashboard. It's caught at the gate. On-call doesn't
   get paged at 2am."

## Gotchas
- **Run-DQX disabled** on a contract with no schemas — use an active aviation
  contract (the button guard is intentional; backend would 422 otherwise).
- **Concurrent-run guard:** a second Run-DQX for the same contract while one is in
  flight returns **409**. Don't double-click on camera; wait for the first.
- The job takes ~60–90s end-to-end — if recording, pre-run so results are warm,
  or cut the wait.
- It pulls the contract as ODCS over HTTP; only **active/approved** contracts are
  pullable (draft → 404 by design).

## Reset between takes
Quarantine + quality items are additive; re-seed for a clean slate, or just
re-run (idempotent enough for the demo — counts stay ~stable on the same data).
