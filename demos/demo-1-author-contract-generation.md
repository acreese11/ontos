# Author — Two Ways to a Published Contract

> **First demo · ~5–6 min.** Alan narrates throughout; **Michael interjects questions to
> keep it conversational** — prompts marked *[Michael Q]* below are optional, drop them in
> as the flow allows. The thesis in miniature: *operating* a contract end-to-end, not just
> writing one. Two ways in — by hand (the full lifecycle) and by AI (Ask Ontos) — same
> contract, same lifecycle. The AI draft is kicked off **first** so its ~96s generation
> hides behind the manual build.

## Run setup (before recording)
- **Tables:** `safe_skies.scheduling.oag_schedule` (manual, T1) · `safe_skies.flight_ops.adsb_v2_raw`
  (AI, T2). Use `adsb_v2_raw` — it's uncontracted, so Ask Ontos drafts in one shot; do **not**
  use `adsb_v2` (already governed by `live_flights`).
- **Create the contracts fresh, live** — post-fix inference now emits correct ODCS types.
  Don't reuse old fixtures (their YAML still shows `ColumnTypeName.STRING`).
- **Personas:** author as a producer; have a **Data Steward** login staged for the approval
  beat (Start Review + Approve are steward-gated).
- **Accept the AI consent gate once** before recording (the first Ask Ontos AI call pops a
  one-time "AI-Powered Analysis" dialog).
- **Connection** configured so Infer-from-Catalog can browse `safe_skies.*`.
- Optional: pin/cache the Ask Ontos output for a deterministic T2.

## Timing (~5:00–5:30)
| Beat | Target |
|---|---|
| 0. Open + Ontos intro | 0:25 |
| 1. Kick off the AI draft | 0:20 |
| 2. Create by hand | 0:30 |
| 3. Infer schema from UC | 0:30 |
| 4. Meaning + quality (narrate content) | 1:00 |
| 5. ODCS YAML reveal | 0:25 |
| 6. Submit → Start Review → Approve | 0:50 |
| 7. Activate + publish | 0:25 |
| 8. Reveal the AI draft | 0:40 |
| 9. Close + pivot | 0:20 |

> The AI generation (~96s) runs during beats 2–7 and is done by beat 8 — nothing to wait on.

## Talk track

**0. Open Ontos + intro**
- **[DO]** Open Ontos (the Contracts list).
- **[SAY]** "This is Ontos — an open-source lifecycle layer for data contracts and products,
  right on Unity Catalog. It's where a raw table becomes a governed, discoverable product:
  you author the contract, enforce it, publish it, and keep it honest — all on the open
  ODCS standard."
- *[Michael Q]* "So when a Boeing team gets a brand-new dataset, where does this start?"
- **[SAY]** "Right here. Today that first question — what's in it, can anyone trust it — is a
  blank YAML file and a week of meetings. Watch how that compresses."

**1. Kick off the AI draft FIRST**
- **[SAY]** "Two ways to author here — by hand, and by AI. I'll set the AI going on one
  table, and build another by hand while it works."
- **[DO]** Ask Ontos → "Draft a data contract for `safe_skies.flight_ops.adsb_v2_raw`." → Send.
  **[SEE]** it starts generating ("Thinking…").
- **[SAY]** "That agent's now reading the table, sampling it, drafting a full contract — in
  the background. We'll come back to it."

**2. Create the contract by hand**
- **[DO]** New Contract → name `oag_schedule`, version `1.0.0`, owner `schedule-data-ops`,
  domain `Scheduling` → Create.
- **[SAY]** "The OAG flight schedule — our published timetable. An empty draft. Let's fill it
  from the data itself."

**3. Infer the schema from Unity Catalog**
- **[DO]** Infer from Catalog → `safe_skies` → `scheduling` → `oag_schedule` → Infer.
  **[SEE]** the columns populate with real types.
- **[SAY]** "Ontos pulls the schema straight from Unity Catalog — columns, types, keys. The
  catalog already knows the structure; that part's free."

**4. Add meaning + quality — narrate the content**
- **[SAY]** "But a schema isn't a contract. Look at what it captured: airline and airport
  codes in both ICAO and IATA, a flight key, scheduled times as real timestamps — and every
  column carries a **classification**." **[DO]** point at a `Restricted`/`Internal` column.
- *[Michael Q]* "Who decides those classifications?"
- **[SAY]** "The contract does — it carries the governance, not a wiki page. That
  classification drives who can see what downstream."
- **[DO]** Add Rule → one quality rule (not-null on `flight_key`). **[SAY]** "And one quality
  rule. Watch — this exact rule compiles into a running DQX check in the next demo. The
  contract becomes the ruleset." *(One line only — the quality story is Enforce's, not Author's.)*

**5. Show the ODCS YAML — make "open" tangible**
- **[DO]** View / Export ODCS → **View ODCS**. **[SEE]** the inline ODCS YAML.
- **[SAY]** "And this isn't our format — it's **ODCS**, the Open Data Contract Standard, an
  open Linux-Foundation spec. Machine-readable, vendor-neutral. The contract's portable —
  not locked to Ontos, or to us."

**6. The lifecycle — submit → review → approve**
- **[DO · producer]** Request… → **Request Data Steward Review**. **[SEE]** **Draft → Proposed**.
- **[SAY]** "The owner doesn't publish on a whim — it goes to a steward."
- **[DO · steward persona]** **Start Review** (→ Under Review) → **Approve** (→ Approved).
- *[Michael Q]* "Could the producer just approve their own?"
- **[SAY]** "No — approval is steward-gated. Three real stages: proposed, under review,
  approved. The human stays in the loop — not a rubber stamp."

**7. Activate + publish**
- **[DO]** Request… → Change Status → **Active**; then **Publish** → scope **Organization** →
  Confirm. **[SEE]** **Active + Published**.
- **[SAY]** "Approved, active, published to the whole organization — discoverable in the
  marketplace, which is the next demo."

**8. Reveal the AI draft**
- **[DO]** Open **Ask Ontos** (running this whole time) — the draft's done; open it.
  **[SEE]** "Draft Contract Created" — full schema, ~9–11 quality rules, classifications,
  SLA, roles.
- **[SAY]** "And while we did that by hand — the agent finished. Same open standard, one ask.
  Totally different shape — telemetry, not a schedule — and it generalized: it sampled the
  real data, inferred types and classifications, and wrote actual quality rules. We didn't
  hand-tune any of this."
- *[Michael Q]* "So from here it's…?"
- **[SAY]** "The same lifecycle — review, approve, publish. The AI just removed the blank page."

**9. Close + pivot**
- **[SAY]** "Two ways in — by hand for control, by AI for speed — same contract, same
  lifecycle. Authoring's the easy part now; *operating* it is the rest of the talk. Next:
  making sure it's actually enforced."

## Reset between takes
Delete the contracts created during the take, or re-seed: `DELETE` then
`POST /api/settings/demo-data/aviation` (see `README.md`). Re-infer any reused contract so
its YAML shows correct ODCS types.

---

# Appendix — analysis & live-run findings

*(Rationale, the 2026-06-14 live-run record, issues + mitigations, structure feedback, and
troubleshooting. The talk track above is the run-ready distillation of all this.)*

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

### Resolution — kick off Ask Ontos FIRST (validated 2026-06-14)

The cleanest fix for the 96 s generation (I-9): **start the Ask Ontos draft at the top
of the demo, then narrate the manual T1 flow while it runs.** The ~96 s overlaps with
the several-minute T1, so by the time we reach T2 the contract is simply *done* — no
dead air, no cover narration. It also upgrades the story: not "watch a spinner" but
"I'll hand table 2 to the agent, build table 1 by hand, and we'll see what it produced"
— an agent working autonomously in the background.

**Validated live (2026-06-14):**
- Kicked off "Draft a contract for `safe_skies.scheduling.oag_schedule_raw`" (an
  *uncontracted* table) — it went **straight to drafting in one shot** (no consent gate,
  no "already governed" detour). Confirms the **I-8 prerequisite**: use an uncontracted
  table so the single prompt drafts immediately.
- **Navigated away** (Contracts → Home) mid-generation: the Ask Ontos panel is a
  persistent app-shell drawer — the in-flight generation **survived the navigation and
  completed on the other page** (9 quality rules, classifications, SLA/roles, "Open in
  editor" link). So you can fire it off, leave to build T1, and the result is waiting.

**Revised demo structure (replaces sequential T1 → T2):**
1. Ontos intro → "I'll set the agent drafting table 2 now" — kick off Ask Ontos on the
   uncontracted telemetry table.
2. Build T1 (OAG schedule) by hand — the full lifecycle (the substance); narrate the
   contract's content (I-12) and pop the View ODCS YAML (I-11).
3. Reveal T2 — the agent's draft is done; open it, contrast control vs. speed.

**Consequences:**
- **I-9 (96 s dead-air): resolved** by this restructure (no longer demo-critical).
- **Streamed generation progress** drops from *demo-critical* to *high-value
  enhancement* — and it *combines* with this: fire off → progress streams in the side
  panel during T1 (ambient "it's working over there") → done by T2. Build it when there's
  time, not before the talk.
- Pre-record/pin still recommended for a deterministic take; for a live take, kicking off
  first is *safer* (more buffer to finish) as long as the prompt is a clean one-shot.
### Flags cleared (2026-06-14)
- **I-8 / T2 table -> `safe_skies.flight_ops.adsb_v2_raw`** (raw ADS-B telemetry,
  uncontracted; drafts in one shot). `adsb_v2` is governed by `live_flights`, so don't use it.
- **Beat 4 quality (I-2) -> manual Add Rule.** Confirmed it persists once a schema exists
  (Quality Rules 0->1); the demo order (infer -> Add Rule) satisfies that. *(Minor UX nit:
  Add Rule on a schema-less contract opens the dialog but silently no-ops -- add the schema
  first.)* **DQX Profile is NOT a demo beat:** it's a remote Databricks job that writes back
  to the metadata DB, which can't reach local Postgres (`POSTGRES_HOST=localhost`) -- so it
  can't run in the local recording setup, and it's slower than Ask Ontos regardless. It's a
  deployed-only capability.
- **Beat 5 ODCS YAML (I-11) -> confirmed.** View / Export ODCS -> **View ODCS** renders the
  ODCS YAML with Copy/Download. *(Contracts inferred before the I-1 fix still show
  `ColumnTypeName.STRING` in the YAML -- record with freshly-inferred contracts.)*
