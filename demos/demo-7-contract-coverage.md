# Demo 7 — Contract Coverage (Maintain)

> **Lifecycle stage: Maintain** · ~1:30–2:00 · the governance-health beat — as the mesh
> scales, is every table governed by exactly one contract? Alan narrates; Michael
> interjects via *[Michael Q]*. **Built + validated end-to-end (2026-06-14)** — unlike
> demo-4 (notification loop) and demo-6 (lakehouse drift), which are both ❌ not built.
> This is the working Maintain beat; a strong candidate to anchor Maintain (and to
> replace the cut-candidate demo-6).

## What it is
A Compliance policy — **"Contract Coverage"** — that walks Unity Catalog and flags tables
with **0 contracts** (ungoverned) or **>1** (conflicting governance), scoped to a catalog:

```
MATCH (t:Object) WHERE t.type IN ['table'] AND t.catalog = 'safe_skies' AND t.schema != 'information_schema'
ASSERT t.contract_count = 1
ON_FAIL FAIL 'Table {name} has {contract_count} contract(s) (expected exactly 1)'
```

## Run setup (before recording)
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

## Talk track

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

## Status
- ✅ **Built + merged** (PR #16 feature, #18 information_schema fix) + validated live.
- vs **demo-4** (notification loop) ❌ not built; **demo-6** (lakehouse drift) ❌ not built
  (cut candidate). Coverage is the Maintain beat that actually works today.

## Possible refinements (see chat 2026-06-14 — mostly deferred)
- **Conflict example:** leave one table double-governed so a live run shows both failure
  modes (currently only the ungoverned case shows). *(The one worth deciding pre-talk.)*
- **Exclude raw/staging** (`*_raw`, `*_quarantine`) for a "true coverage" metric — but
  keeping `adsb_v2_raw` flagged ties nicely back to the Author demo (the gap we fill with AI).
- **Severity split** via the DSL's CASE/WHEN: `>1` = error (conflict), `0` = warning
  (ungoverned). Richer, but more complexity — optional polish.
