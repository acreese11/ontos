# Design & Plan: Unify Quality-Rule Authoring on DQX-Native ODCS

**Status:** design draft (for review). No implementation yet.
**Companion analysis:** `docs/notes/quality-rules-ux-analysis.md` (the diagnosis this builds on).
**DQX version:** **0.15.0** (latest, published 2026-06-13). Design targets 0.15.0.
> The local pip mirror (Databricks proxy) lags at 0.14.0 and PyPI is firewalled in dev, so
> 0.15.0 was verified via the GitHub release API. The investigation below was done against the
> locally-installed 0.14.0; 0.15.0 changes to the ODCS path are **additive only** (no
> restructuring of `contract_rules_generator.py`'s ODCS handling), and it ships one fix we
> rely on — see §3 (LLM-import) and §11 Phase 0.

---

## 1. Goal

One coherent, **readable** journey for authoring data-quality rules that **actually
execute**, defaulting to **DQX**, where *the thing you author is the thing DQX runs*.
Other engines remain expressible (the ODCS `engine` field) but are **not** the default
journey. The same model must be produced by the **agentic contract generator**, and the
story must land in the **demo talk track** — emphasizing that DQX reads ODCS natively.

## 2. The problem in one paragraph (see analysis note for detail)

Ontos has three quality-authoring surfaces (contract-level dialog, per-column editor tab,
the AI generator) that all emit a human-readable `rule` *text* with **no executable
`implementation`**. DQX's contract-rules generator only executes an explicit rule when it
is `type=custom` + `engine=dqx` + `implementation={check:{function, arguments}}`
(`_is_dqx_explicit_rule`, `datacontract/contract_rules_generator.py`); anything else is
silently skipped (or needs the disabled LLM text path). So **only the seed's hand-authored
rules run**; everything authored in the UI or by the generator is inert. Column-level rules
are additionally dropped on save, and editing a rule strips its `implementation`.

**Root cause:** there is no way to produce the DQX-executable form except hand-writing the
`implementation` dict.

## 3. What DQX already gives us (don't rebuild it)

DQX 0.14's `DataContractRulesGenerator.generate_rules_from_contract` (called by
`workflows/dqx_contract_validation/dqx_contract_validation.py`) produces three classes of
rule from an ODCS contract — Ontos already runs it with predefined + schema-validation on:

1. **Schema-validation** (`generate_schema_validation=True`) → one `has_valid_schema` per
   schema (columns/types/order).
2. **Predefined from property constraints** (`generate_predefined_rules=True`) — DQX turns
   ODCS property fields into column checks automatically:
   | ODCS property field | DQX check generated |
   |---|---|
   | `required: true` | `is_not_null` |
   | `unique: true` | `is_unique` |
   | `logicalTypeOptions.pattern` | `regex_match` |
   | `logicalTypeOptions.minimum`/`maximum` | range (`sql_expression`) |
   Ontos already exports `required`/`unique`/`logicalTypeOptions` (data_contracts_manager.py
   ~1014–1055), so **these checks already run today** from the schema editor's Constraints tab.
3. **Explicit DQX rules** (object- *and* property-level) — `_extract_property_explicit_rules`
   reads `prop.quality`, `_extract_schema_explicit_rules` reads `schema_obj.quality`; both
   require `type=custom` + `engine=dqx` + `implementation.check`. **This is the path for
   custom column-level and object-level rules**, and DQX runs it natively.

(There is also a `process_text_rules` LLM path that compiles free text → checks. It needs the
`[llm]` extra and a serving endpoint **at execution time** — nondeterministic, currently
disabled. We keep it **off** by default; see §9.)

> **LLM-import fix lands in 0.15.0.** The runner currently ships a `sys.modules` stub
> (commented as databricks/dqx#1168) to dodge the *unconditional* `DQLLMEngine` import in
> `contract_rules_generator.py` that breaks contract rule-gen when the `[llm]` extra isn't
> installed. **0.15.0 fixes this (#1191 — our own upstream PR).** Upgrading lets us **delete
> the stub** (§11 Phase 0) — and it's a nice talk-track beat: we fixed, upstream, the bug that
> blocked native ODCS rule generation.

**Implication:** we don't need an intent DSL or a custom compiler. We need Ontos to author in
the two DQX-native forms — **property constraints** and **explicit DQX checks** — and put them
where DQX reads.

## 4. The DQX check catalog (the vocabulary — from `databricks/labs/dqx/check_funcs.py`)

These are the built-in checks the authoring UI offers (each becomes
`implementation.check = {function, arguments}`). Categorized by grain:

**Column-scoped (offered on a column / property):**
`is_not_null` · `is_not_null_and_not_empty` · `is_not_empty` · `is_in_list` ·
`is_not_in_list` · `is_not_null_and_is_in_list` · `is_in_range` · `is_not_in_range` ·
`is_equal_to` · `is_not_equal_to` · `is_not_less_than` · `is_not_greater_than` ·
`regex_match` · `is_valid_email` *(0.15)* · `is_valid_date` · `is_valid_timestamp` ·
`is_not_null_and_not_empty_array` · `is_valid_json` · `has_json_keys` · `has_valid_json_schema` ·
`is_older_than_n_days` · `is_not_in_future` · `is_not_in_near_future` · `is_data_fresh` ·
`is_geo_contains`/`is_geo_covers`/`is_geo_intersects`/`is_geo_touches`/`is_geo_within` *(0.15)* ·
**`sql_expression`** (escape hatch)

**Dataset / aggregate / multi-column (offered at the schema-object level):**
`is_unique` · `foreign_key` · `is_aggr_not_greater_than` · `is_aggr_not_less_than` ·
`is_aggr_equal` · `is_aggr_not_equal` · `has_no_outliers` · `has_no_aggr_outliers` ·
`has_no_row_anomalies` · `has_valid_schema` · `compare_datasets` ·
`is_data_fresh_per_time_window` · `sql_query`

> **Aviation fit:** the `is_geo_*` checks (0.15) are a natural beat for the Safe Skies demo —
> e.g. `lat`/`lon` within an expected airspace polygon — worth considering for the Author/Enforce
> talk track if time allows.
> **Anomaly checks make LLM calls now:** in 0.15, `has_no_row_anomalies` defaults
> `enable_ai_explanation=True` → it calls a Model Serving endpoint at run time. If we use
> anomaly checks, set `enable_ai_explanation=False` for deterministic recording — or lean in and
> *show* the AI explanation as a feature. Either way, a deliberate choice, not a default to inherit.

Each catalog entry carries: a plain-language **label** ("In range", "Matches pattern",
"In allowed list", "Unique", "Fresh within N days"), an **arguments schema** (typed fields),
and a **grain** (column vs object). `sql_expression`/`sql_query` are the universal escape
hatches where the author writes a predicate directly.

> v1 demo subset (surface these first; full catalog behind "more"):
> `is_not_null`, `is_in_range`, `is_in_list`, `regex_match`, `is_unique`,
> `is_data_fresh`, `is_aggr_not_greater_than`, `sql_expression`.

## 5. The authoring user journey (the priority)

The model is the same at every grain; the entry point differs.

### 5a. Column-level (schema editor → property → **Quality** tab)
1. Open a column, **Quality** tab → **Add check**.
2. Pick a check from a **categorized, searchable list** of column-scoped DQX checks
   (plain-language labels, not function names front-and-center).
3. Fill **typed arguments** — the **column is pre-filled**; the rest are the check's params
   (e.g. `is_in_range` → min/max; `is_in_list` → allowed values; `regex_match` → pattern).
4. Set **criticality** (error / warn) and optional **governance metadata**
   (`dimension`, `businessImpact`) used by the trust loop + compliance scoring.
5. **Escape hatch:** "Custom SQL expression" → write a predicate (e.g.
   `scheduled_arr_utc > scheduled_dep_utc`). The SQL shown *is* the SQL DQX runs.
6. Save → Ontos wraps the choice as
   `{type:"custom", engine:"dqx", implementation:{check:{function, arguments}}, name, criticality, dimension, businessImpact}`
   and persists it on the property (`property_id`).

### 5b. Object-level (contract details → schema object → quality)
Same flow, but the list offers **dataset/aggregate** checks (`is_unique`, `foreign_key`,
`is_aggr_*`, `has_no_aggr_outliers`, `sql_query`, …). Persisted on the object (`object_id`).

### 5c. Constraints stay where they belong
Declarative single-column facts (`required`, `unique`, `pattern`, `min`/`max`, `length`)
are authored in the **Constraints** tab as today; DQX auto-generates their checks. The
Quality tab shows these **constraint-derived checks read-only alongside** the explicit ones,
so authors see "icao24 already has a pattern check from its constraint" and don't duplicate.
(Resolves the seed's literal duplication — see §10.)

### What the author sees vs what runs
The list item renders the readable form ("**icao24** — Matches pattern `^[0-9A-F]{6}$`"),
which is *derived from* the stored `implementation.check`. There is **no separate free-text
`rule` field** to drift from the executable check — the display string is generated. This
eliminates the cosmetic/executable split and the edit-strip bug by construction.

## 6. Storage / model changes

- Keep `DataQualityCheckDb`. `engine` **defaults to `"dqx"`**. `implementation` (JSON) holds
  the `{check:{function, arguments}}` dict — the single source of truth for execution.
- Grain via `object_id` (object-level) / `property_id` (column-level), both already in the model.
- The legacy free-text `rule` column becomes **derived/display-only** (kept for back-compat
  + the `sql_expression` raw text), no longer an independent authoring field.
- `mustBe*` columns: **fold into catalog checks** (`is_in_range`, `is_not_less_than`, …). They
  were stored-but-never-executed; the catalog forms execute. Migrate/deprecate.

## 7. The envelope (the only "compiler" — ~a helper, not a DSL)

A small backend module owns:
- the **catalog** (function → {label, args schema, grain}),
- `build_implementation(function, arguments)` → the `{check:{function, arguments}}` dict,
- `to_display(check)` → the readable string,
- validation that `arguments` match the function's schema.

**Correctness gate:** unit-test that `build_implementation` reproduces the existing aviation
seed's hand-authored `implementation` **byte-for-byte** for every `_qrule` (proves we match
known-good DQX-runnable output before we touch any surface).

## 8. Agentic contract generator integration (required)

The generator must emit the *same* DQX-native model — not free text:

- **Constraints:** from the column stats/samples it already inspects, set property
  `required`/`unique`/`pattern`/`minimum`/`maximum` → DQX predefined checks (no quality rule).
- **Explicit DQX checks:** for things constraints can't express, emit catalog checks
  (`is_in_range`, `is_in_list`, `regex_match`, aggregate, `sql_expression`) at the right grain,
  wrapped via the §7 envelope → executable, deterministic, **no runtime LLM**.
- **Prompt rework** (`contract_generator_manager.py` `SYSTEM_PROMPT`): replace "write `rule`
  (English or SQL-like)" with the **DQX check catalog + argument shapes**, instructing the
  model to (a) prefer constraints for declarative facts, (b) choose a catalog `function` +
  `arguments` grounded in observed patterns, (c) column-scope where applicable, (d) use
  `sql_expression` only when no catalog function fits. Output validated against the catalog
  in `_finalize_contract`.
- **Result:** AI-generated contracts ship rules that *run* in DQX — the headline payoff.

## 9. Engine default + extensibility

- **Default engine = `dqx`** for the journey above. The catalog, envelope, and prompt are
  DQX-shaped.
- **Other engines not eliminated:** the ODCS `engine` field is retained; a rule may carry a
  non-DQX `engine`/`implementation` and round-trip. There is simply no guided UI journey for
  them in v1 (custom SQL covers most cross-engine needs).
- **DQX text-rule LLM path:** kept **off** by default (nondeterministic at execution time,
  needs `[llm]` extra + endpoint, blocked by #1168). Revisit post-demo as an optional
  "describe a check in English" authoring aid that compiles to a catalog check *at author
  time* (deterministic) rather than at run time.

## 10. Demo talk-track integration (required)

The unification must show up in the recorded demos, with one through-line:
**"Ontos doesn't invent a quality DSL — it authors ODCS quality that DQX executes natively.
The contract is the ruleset."**

- **Author (demo-1):** when the AI generates the contract, show it producing a real DQX check
  (e.g. `is_in_range` on `alt_baro_ft`, `regex_match` on `icao24`) — and call out that these
  are the *exact* checks DQX will run, not descriptions. Replaces the current "inert text" gap.
- **Enforce (demo-2):** emphasize **DQX reads the ODCS contract natively** — the contract's
  quality section *is* the DQX ruleset, no translation layer. Show a check authored in Ontos
  running unchanged in DQX (`_is_dqx_explicit_rule` consumes it as-is). This is the strongest
  "engineering trust" beat — author once, enforce natively.
- **Maintain (demo-4):** the same contract drives both the schema-drift check (Part A) and the
  DQX quality run; one contract, two guardrails. (Already partly threaded.)
- **Optional credibility beat:** the upstream fix that *enables* clean native ODCS rule
  generation without the `[llm]` extra (DQX #1191) is **our own contribution**, shipping in
  0.15.0. A natural aside in Enforce — "we didn't just consume DQX, we fixed the gap that
  blocked contract-native rule generation, upstream."
- **Update `demos/demo-1-*` and `demos/demo-2-*`** talk tracks in the implementation phase
  (PR #22 branch is the home for demo-2/3 edits).

## 11. Phased plan

| Phase | Scope | Output |
|---|---|---|
| **0** | Bump DQX pin `>=0.11.0` → **`>=0.15.0`** in `dqx_contract_validation.yaml`; **remove the `sys.modules` LLM-import stub** in the runner (fixed upstream by #1191 in 0.15.0). Verify at deploy time (0.15.0 not installable in local dev — firewalled mirror; the workflow installs it remotely). | tiny PR |
| **1** | **Envelope + catalog** backend module (§7) + the byte-for-byte seed-reproduction test. No UI yet. | backend PR |
| **2** | **Authoring UI** — the check picker (catalog + sql_expression) at column & object grain; derived display string; retire the free-text `rule` dialog. | frontend PR |
| **3** | **Persistence fixes** — read/persist `property.quality` with `property_id` (the dropped column write); edit derives `implementation` (kills the strip bug). | backend PR |
| **4** | **Generator** — emit constraints + catalog DQX checks; prompt rework; validation; tests (§8). | backend PR |
| **5** | **Talk track + cleanup** — demo-1/2 edits (§10); remove the `rcvr_cntry_code` sample-injection; retire the inert-text path; migrate `mustBe*`. | docs + cleanup PR |

Sequencing rationale: Phase 1 proves the envelope against known-good DQX output before any
surface depends on it; Phases 2–4 each become executable independently; Phase 5 lands the story.

## 12. Open questions / decisions for review

1. **Constraint vs explicit-check overlap.** When an author picks `is_not_null`/`regex_match`
   on a column that *could* be a constraint, do we (a) nudge "set this as a constraint instead"
   (constraints are cleaner + auto-generate), (b) allow both and de-dupe on ODCS emit, or
   (c) not worry about it? Recommend (a) nudge + (b) de-dupe as a safety net.
2. **v1 catalog subset** (the demo set in §4) vs exposing the full catalog immediately.
   Recommend the subset front-and-center, full list behind "more checks".
3. **Governance metadata** (`dimension`/`businessImpact`/`severity`→`criticality`) — keep
   per-rule for the trust loop / compliance score (yes, recommend keep).
4. **Back-compat / migration** for existing contracts whose rules are loose `rule` text with
   no `implementation`: attempt envelope inference where the text maps to a known function,
   else mark "needs re-authoring". Scope TBD.

## 13. Key references
- DQX: `databricks/labs/dqx/datacontract/contract_rules_generator.py` (`_is_dqx_explicit_rule`,
  `_extract_property_explicit_rules`, `_generate_rules_from_logical_type_options`),
  `databricks/labs/dqx/check_funcs.py` (the catalog),
  docs: https://databrickslabs.github.io/dqx/docs/reference/quality_checks/
- Ontos: `controller/data_contracts_manager.py` (`_create_schema_objects` write @1747,
  `_create_quality_checks` @1956, property-quality read @1162–1226, ODCS export @1014–1055),
  `controller/contract_generator_manager.py` (`SYSTEM_PROMPT` @82, `_finalize_contract` @120),
  `components/data-contracts/quality-rule-form-dialog.tsx`,
  `components/data-contracts/schema-property-editor.tsx` (Quality tab),
  `workflows/dqx_contract_validation/dqx_contract_validation.py` (the runner).
