# Author — Two Ways to a Published Contract

> **Lifecycle stage: Author** (first demo — introduces Ontos) · **~5:30–6:00** ·
> the richest demo: the thesis in miniature (operating a contract, not just writing
> one). Co-narrated: **Michael** = business framing + the human/governance beat,
> **Alan** = technical mechanics. Pre-recorded, narrated live.

**The structure — two ways to author the same kind of contract:**
- **Table 1 (OAG schedule) — by hand:** the governed craft + the full lifecycle
  (Infer-from-Catalog → enrich → review → approve → publish). The *substance*.
- **Table 2 (ADS-B telemetry) — via Ask Ontos:** the AI/agent path. One ask drafts
  a complete ODCS contract. The fast coda + the agent showcase.

Two modes defuse "you cherry-picked the table" **and** contrast control vs. speed.

**Readiness:** *(corrected by the 2026-06-14 live run — see "Live-run findings" below;
several scripted beats need fixes/changes first.)*
- ✅ Manual path core works: New Contract → Infer-from-Catalog (remote UC) → lifecycle →
  publish. ⚠️ but the **enrich** beats are broken (semantic-link I-4, DQX-profile I-2)
  and the inferred **type display** is buggy (I-1, shows `ColumnTypeName.STRING`).
- ⚠️ AI path: the generator works end to end, **but took 95.8 s** (not 10–30s),
  `adsb_v2` is **already governed** (I-8), and there's a one-time consent gate (I-10).
  Pre-record T2; pin/cache for determinism.
- ⚠️ Approval: the **Approve button on `proposed` 500s** — must hop through Under Review
  (I-3). The persona switch still needs a recording pass.

**The point:** AI removes the blank page — but that's the *easy* sliver. The real
substance is **operating the lifecycle**: infer → enrich → review → approve →
publish. *That's* operating a contract, not just defining one. Two ways in, same
contract, same lifecycle.

## USER-GUIDE points covered
Ontos intro (first appearance) · Infer-from-Catalog (structural UC schema) ·
5-step authoring wizard · semantic-concept linking (the ontology) ·
DQX-suggested quality rules · **ODCS introduced** (open standard, Linux Foundation,
portable) · contract lifecycle states (Draft → Proposed → Approved → Active) ·
Submit-for-Review / Steward approval · change-status to Active · request-publish
(discoverable) · **Ask Ontos AI generation** (agent invokes the generator).
**Out of scope here:** Compliance DSL (→ Enforce), Products/marketplace (→ Discover).

## Visual reality (what's actually on screen)
- The on-screen payoff is the **structured contract** (schema table, quality rules,
  per-column classification) plus the **Ask Ontos conversation**.
- **YAML reveal IS available now** (updated 2026-06-14): the header **View / Export ODCS
  → View ODCS** opens a modal of the inline ODCS YAML (added in PR #11). The earlier
  "no YAML reveal" note is stale — use this modal to make the ODCS-intro beat tangible
  (show the open, portable spec). *Not exercised in the live run — validate it (I-11).*
- **No ICAO/PII badges.** PII is a per-column `classification` (Public/Internal/
  Restricted) + a `containsPII` custom property — narrate "classification," not a badge.

## Timing budget (~5:30–6:00)
| Sub-beat | Target |
|---|---|
| Ontos intro + the dataset (Michael→Alan) | 0:30 |
| **T1** Create + Infer from Catalog (schema from UC) | 0:40 |
| **T1** Enrich — semantic link + DQX-suggested quality rule | 1:00 |
| **T1** Contract reveal + **ODCS intro** | 0:30 |
| **T1** Review → approve — Draft→Proposed→Approved (steward) | 0:50 |
| **T1** Set Active + publish (discoverable) | 0:30 |
| **T2** Ask Ontos drafts the ADS-B contract (+ cover narration) | 1:00 |
| Close + pivot (Alan) | 0:30 |

> ⚠️ Tight. For a hard 5:00, trim the T1 enrichment (drop the semantic-link or the
> DQX-suggestion beat). Pin the Ask Ontos output so T2 is deterministic on camera.

## Pre-flight
- Two raw UC tables for the two paths:
  - `safe_skies.scheduling.oag_schedule` (OAG-style schedule) — the **manual** table (uncontracted ✓).
  - ⚠️ `safe_skies.flight_ops.adsb_v2` (ADS-B telemetry) is **already governed** by the
    `live_flights` contract — for the **Ask Ontos** path pick a genuinely *uncontracted*
    telemetry table, or it won't draft fresh (I-8).
- **Accept the AI consent gate** once before recording (I-10); **install
  `dqx_profile_datasets`** (Settings > Jobs) if keeping the DQX-suggestion beat (I-2).
- **Producer / domain-owner** persona for authoring; **Data Steward** persona staged
  for the approval beat (persona switch so Draft→Proposed→Approved shows on camera).
- A connection configured so **Infer-from-Catalog** can browse `safe_skies.*`.
- **Ask Ontos** reachable and able to invoke the contract-generator (verified).
- Pin/cache the Ask Ontos generation for a deterministic recording.

## Walkthrough

1. **[SAY · Michael]** "When a Boeing domain team gets a new dataset, the first
   question is *what's in it, and can anyone trust it?* Today that's a blank YAML
   file and a week of meetings."
2. **[SAY · Alan]** "This is Ontos — the lifecycle layer for data contracts and
   products on Unity Catalog. There are two ways to author a contract here. Let's do
   the first by hand — the OAG flight schedule."
   **[DO]** Create contract (name, version, owner, domain). **[SEE]** Draft created.
3. **[SAY · Alan]** "Ontos pulls the schema straight from Unity Catalog — columns,
   types, keys. The catalog already knows the structure." **[DO]** Infer from
   Catalog → pick `oag_schedule`. **[SEE]** Schema populated.
4. **[SAY · Alan]** "Then we add the meaning. We tie columns to business concepts —
   not just types — that's the ontology under Ontos." **[DO]** Link a column to a
   business concept. **[SEE]** Concept chip. **[SAY · Alan]** "And for quality, Ontos
   profiles the data and suggests rules — I'll accept these; we'll see them enforced
   in a minute." **[DO]** Accept a DQX-suggested quality rule.
5. **[SEE]** The structured contract — schema, quality rules, classification.
   **[SAY · Alan, ODCS intro]** "And this format isn't ours — it's **ODCS**, the
   Open Data Contract Standard. An open, Linux-Foundation spec: machine-readable and
   vendor-neutral. The contract stays portable — not locked to Ontos, or to us."
6. **[SAY · Michael]** "The owner doesn't publish on a whim." **[DO]** Submit for
   Review. **[SEE]** **Draft → Proposed**. **[DO · steward persona]** Steward
   approves. **[SEE]** **Proposed → Approved**. **[SAY · Michael]** "A steward signs
   off — the human stays in the loop."
7. **[SAY · Alan]** "Approved — set it Active and publish." **[DO]** change-status →
   Active; request-publish (scope = organization). **[SEE]** **Active + Published** —
   now discoverable.
8. **[SAY · Alan, transition]** "That's by hand. But you don't have to do it by hand."
   **[DO]** Open **Ask Ontos** → "Draft a contract for the `adsb_v2` telemetry table."
   **[COVER · while it generates ~15–20s — no dead air]**
   - **[Alan]** "While it drafts — it's doing what we just did by hand, in one pass:
     reading the table from the catalog, profiling it, inferring types and quality
     rules, writing a valid ODCS contract. The agent isn't guessing from names — it's
     working from the real data."
   **[SEE]** Ask Ontos returns a complete ODCS draft contract.
9. **[SAY · Alan]** "Same standard, one ask — AI removes the blank page. Totally
   different shape, telemetry not a schedule — and it generalizes. From here, it's
   the same lifecycle." *(Don't re-run the lifecycle — reference it.)*
10. **[SAY · Alan, close + pivot]** "Two ways in — by hand for control, by AI for
    speed — same contract, same lifecycle. Authoring's the easy part now; *operating*
    it is the rest of the talk. Now let's make sure it's actually enforced."

## Gotchas
- **opus-4.x rejects `temperature`** — fixed via `llm_client.chat_completion`
  (retries without it). If a *new* table errors with `BAD_REQUEST … temperature`,
  the call path didn't go through that helper.
- **Identifier validation**: catalog/schema/table must be plain identifiers — a bad
  name returns **422** (not a crash). Use the real `safe_skies.*` tables.
- **Publish 403** — the `data-contracts: READ_WRITE` gate; confirm the recording
  persona has write (or a transient Lakebase reconnect).
- **Approval needs two personas** — a producer can't approve their own contract;
  stage the steward approval (persona switch) or the state won't transition.
- **Ask Ontos latency** — pin/cache the generated contract so T2 is deterministic.

## Reset between takes
Delete the draft/published contracts, or re-seed:
`DELETE` then `POST /api/settings/demo-data/aviation` (see `README.md`).
- Live-run fixtures left behind (2026-06-14, delete before a clean take): `oag_schedule`
  (now approved + published) and `adsb_v2_flight_tracking_data` (AI-drafted draft).

## Live-run findings (2026-06-14)

Drove the **full** Author flow live in the local app (backend :8000 + frontend :3000,
local/mock **admin**) against the **remote** `safe_skies` UC. Where this conflicts with
the optimistic "Readiness" notes above, **this section wins.**

### Steps actually taken — T1 (by hand)
1. Contracts → **New Contract**: name `oag_schedule`, version `1.0.0`, status draft,
   owner team `schedule-data-ops`, domain `Scheduling` → created. *(Landed back on the
   list, not the new contract — see I-6.)*
2. Filtered the list to `oag_schedule`, opened it.
3. **Infer from Catalog** → Databricks UC connection → browsed `safe_skies` → `scheduling`
   → checked `oag_schedule` → **Infer 1 Schema**. Pulled **18 columns** (aircraft/airline/
   airport ICAO+IATA codes, `flight_key`, …). *Catalog browse against remote UC works.*
4. **Profile with DQX** → selected the schema → **Profile** → **failed** (see I-2).
5. **Request… → Request Data Steward Review** → `draft → proposed`. ✓
6. Header **Approve** (on `proposed`) → **500** (see I-3). Workaround that worked:
   **Request… → Change Status → Under Review** (`proposed → under_review`), then header
   **Approve** (`under_review → approved`). ✓
7. **Publish** → scope **Organization** → **Confirm** → Published. ✓ *(Published from
   `approved`; publication scope is a separate dimension from lifecycle status — so
   "Active + Published" in the script is really "approved/active + Published". `approved
   → active` is the same Change-Status flow if you want the status to read Active.)*

### Steps actually taken — T2 (Ask Ontos)
8. Ask Ontos: *"Draft a data contract for `safe_skies.flight_ops.adsb_v2`…"* → one-time
   **AI consent gate** (see I-10) → the agent replied that `adsb_v2` is **already governed**
   by the `live_flights` contract + "Live ADS-B Telemetry" product, and asked how to
   proceed (see I-8). It did **not** draft fresh.
9. Replied *"create a new draft anyway, fresh analysis"* → generated
   `adsb_v2_flight_tracking_data` (Draft, 18 cols, **11 quality rules**, classifications,
   SLA, roles) in **95.8 seconds** (see I-9). The generator works end to end.

### Issues & mitigations
| # | Issue | Type | Fix / mitigation |
|---|---|---|---|
| I-1 | Inferred `logicalType` persists as `ColumnTypeName.STRING` (every row, in the schema reveal); `physicalType` is fine (`string`) | code bug | Map UC `ColumnTypeName` → ODCS logical type in `connectors/databricks.py:656` & `:730` (don't `str()` the enum). Persisted → **re-infer** after the fix. → bug-fix PR |
| I-2 | **DQX Profile** fails: `dqx_profile_datasets` workflow not installed → 400 "Invalid profiling request" (real cause masked) | setup + error-UX | Install the workflow via **Settings > Jobs** before recording + improve the error msg. If left uninstalled, **drop the DQX-suggestion beat** and add one rule manually. |
| I-3 | **Approve broken**: UI offers Approve on `proposed`, but the state machine needs `proposed → under_review → approved`; the direct call 500s, **silently** | code bug (blocker) | Allow `proposed→approved`, OR have Approve auto-hop `under_review`, OR only show Approve on `under_review` + add a "Start Review" action. Demo workaround: Change Status → Under Review → Approve. → bug-fix PR |
| I-4 | **Semantic linking**: no per-column concept affordance on the schema rows; the contract-level "Add" opened nothing | UI ↔ script | Decide: concepts at the **contract level**, or drop the "tie *columns* to concepts" claim, or build per-column linking. Rework script step 4. |
| I-5 | `_rescued_data` is the **first** schema row (Databricks ingestion artifact, not a business field) | data/cosmetic | Strip `_`-prefixed system cols on infer, or clean the source table, or delete the column in the take. |
| I-6 | After **Create**, returns to the list (new contract on page 2), no auto-open | UX | Auto-open the created contract, or filter to it on camera. |
| I-7 | **Silent failures**: both the DQX 400 and the Approve 500 showed **no error toast** — the contract just didn't change | error-UX | Surface destructive toasts on these failures. → bug-fix PR (with I-3) |
| I-8 | **T2 premise is wrong**: `adsb_v2` is already governed (`live_flights`), so the AI won't draft fresh — it asks to clarify | demo data / script | Use a genuinely **uncontracted** telemetry table for T2, or remove `live_flights` from the seed, or script the "create anyway" path explicitly. |
| I-9 | Ask Ontos generation took **95.8 s** (doc assumed 10–30s) | perf / demo | **Pre-record T2** and speed-ramp; pin/cache for determinism. Also motivates the streamed-progress feature below. |
| I-10 | One-time **AI consent gate** ("AI-Powered Analysis") before the first Ask Ontos AI call | UX | **Accept it before recording** so it doesn't pop on camera (added to pre-flight). |
| I-11 | **YAML preview never exercised** — the live run never opened **View / Export ODCS → View ODCS**, so the inline-YAML modal (PR #11) is unverified, and the ODCS-intro beat currently shows no actual spec | gap / script | Validate the View ODCS modal; **use it in the ODCS-intro beat** to show the real, portable YAML (makes "open standard" concrete instead of asserted). |
| I-12 | **Contract content is never explained** — the walkthrough narrates *mechanics* (infer, enrich, approve, publish) but never says what's actually *in* the contract (which columns, what the inferred quality rules check, which columns got which classification) | script / emphasis | At the reveal, **call out specific content**: name a couple inferred columns, read one generated quality rule, point at a `Restricted` classification. The substance is the payoff — don't click past it. |

### Feature idea: streamed generation progress (chain-of-thought)
The 96 s of static "Thinking…" is untenable live. The pipeline already runs discrete
stages (inspect schema → sample 20 rows → compute stats → AI draft → infer
classifications → generate quality rules → SLA/roles) — surface them **live** as a
running checklist in the Ask Ontos panel. Deterministic stage-progress is recommended
for the recorded take (controllable on camera); an optional streamed LLM-reasoning line
during the draft stage is a stretch goal. Own branch+PR; it rescues the T2 beat by
turning dead air into narratable progress.

### Structure / emphasis feedback
- **Make T1 (manual, the lifecycle) unambiguously the star; demote T2 to a short,
  pre-recorded punctuation.** Reality reinforces the doc's own thesis ("AI removes the
  blank page — the easy part"): the AI path is the *slow, finicky* one (96 s, consent
  gate, already-governed detour). Don't let it become the centerpiece.
- **The enrich sub-beat is the shakiest part of T1** — both halves are broken right now
  (semantic-link has no clean UI path, I-4; DQX-suggest needs an uninstalled workflow,
  I-2). Consider simplifying enrich to what inference *already* produces (schema +
  per-column classification) plus **one manually-added quality rule** — lower risk, same
  narrative ("we add meaning and quality").
- **Lean into the lifecycle — it's the differentiated story and it works.** The
  `proposed → under_review → approved` path is a *richer* governance beat than the
  scripted "Proposed → Approved": embrace `under_review` as a real review stage rather
  than a step to skip. That plus publish/scope is the "operating a contract" thesis made
  concrete — the part no blank-page-AI demo has.
- **Re-time around a pre-recorded ~96 s T2.** The 5:30–6:00 budget assumed a ~1:00 live
  T2; with T2 pre-recorded/ramped you control its on-screen length, so only the live
  narration time counts.
- **Explain the content, not just the mechanics (I-12).** The current script is a tour of
  *clicks*. The audience came for the *substance* — what a good contract contains. At the
  reveal, slow down and narrate the actual inferred schema, a quality rule, a
  classification, and pop the **View ODCS** YAML (I-11) so the "open, portable standard"
  is shown, not claimed. This is the single highest-leverage script change.
