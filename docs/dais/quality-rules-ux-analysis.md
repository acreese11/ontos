# Quality Rules: model, DQX mapping, and UX gaps

**Status:** analysis only (no code changes in this note).
**Trigger:** "The quality rules expressed in Ontos are hard to understand / not
intuitive to write. How does the syntax shown map to how DQX expects rules?
I'm only seeing quality rules at the contract level — what about
schema/column level?"

This note answers three questions — (A) what the model is and why it confuses,
(B) how the visible syntax maps to what DQX actually runs, (C) whether
column/schema-level rules work — and ends with concrete UX recommendations.
All claims below were traced through the code (file:line cited).

---

## TL;DR

1. **The "Rule Expression" you type is mostly documentation.** What DQX actually
   executes lives in separate, **UI-hidden** fields: `implementation` / `engine`
   (and the `mustBe*` comparators). The displayed `rule` text (e.g.
   `icao24 matches '^...'`) is cosmetic; the executed check is the
   `implementation` (e.g. a DQX `sql_expression` like `icao24 rlike '^...'`).

2. **Editing a rule in the UI silently disables it (confirmed bug).** The Edit
   Quality Rule dialog never carries `implementation`/`engine`/`mustBe*`, and the
   save path deletes-and-recreates the check from the dialog payload — so
   **saving an edited rule nulls its executable part while leaving the
   human-readable text intact.** The rule still *looks* defined.

3. **Column/property-level rules are modeled and import correctly, but you can't
   author or target them per-column in the UI.** The dialog has a `property`
   level option but no column binding, and every rule created via the UI is
   attached to the *first* schema object regardless.

---

## A. The data model (and why it's confusing)

`DataQualityCheckDb` (`src/backend/src/db_models/data_contracts.py`) carries a
wide column set. They fall into three buckets:

| Bucket | Columns | Role |
| --- | --- | --- |
| **Metadata** | `name`, `description`, `level`, `dimension`, `business_impact`, `severity`, `type` | Documentation + criticality. Drives *how* a failure is reported, not *what* is checked. |
| **Executable** | `rule`, `query`, `engine`, `implementation`, `must_be*` | What actually gets run. `implementation` holds the DQX check spec; `engine` selects the executor; `rule`/`query` are library-function / SQL forms; `must_be*` are comparator shortcuts. |
| **Scheduling** | `method`, `schedule`, `scheduler`, `unit`, `tags` | When/how it runs. |

The confusion is structural: the UI surfaces a free-text **"Rule Expression"**
bound to `rule`, which reads like the check (`icao24 matches '^...'`) but is
*not* what executes. The executable fields (`implementation`/`engine`/`mustBe*`)
are absent from the editing surface entirely. So you author in a field that
documents, while the field that runs is hidden — and, per §B, can be wiped.

Two creation surfaces fill different subsets:
- **ODCS import** (`_create_quality_checks`, `data_contracts_manager.py:1956`)
  reads the full set including `implementation`/`engine`/`mustBe*`
  (lines 1995–2004). Imported/seeded rules are complete and executable.
- **The UI dialog** (`quality-rule-form-dialog.tsx`) fills only 9 fields
  (name, description, level, dimension, businessImpact, severity, type, query,
  rule). It never touches `implementation`/`engine`/`mustBe*`.

---

## B. How the visible syntax maps to DQX

DQX expects checks as a list of `{check: {function, arguments}, criticality,
name}` entries (or `sql_expression` checks). In Ontos that spec is stored in the
`implementation` column (with `engine` selecting the executor); the human-facing
`rule` text is parallel documentation.

Worked example (a seeded `icao24` rule):
- **Displayed** (`rule`): `icao24 matches '^[0-9a-fA-F]{6}$'` — reads like a check, runs nothing.
- **Executed** (`implementation.check.sql_expression`): `icao24 rlike '^[0-9a-fA-F]{6}$'` — this is what DQX evaluates.

So "DQX reads the ODCS contract natively" is accurate, but it reads the
**`implementation`**, not the pretty expression. For a live walkthrough, narrate
the check as the `implementation`/SQL DQX runs — not the `rule` text.

### The footgun (confirmed bug): editing a rule strips its executable part

Chain, end to end:

1. **Dialog** (`quality-rule-form-dialog.tsx:71-79`) builds a fresh rule object
   from form state containing only the 9 metadata/`rule`/`query` fields. It does
   not read `initial.implementation`/`initial.engine`/`mustBe*` into state, so
   they are absent from the submitted object.
2. **Parent edit handler** (`views/data-contract-details.tsx:1140-1143`)
   *replaces* the array entry: `updatedRules[editingQualityRuleIndex] = rule`
   (the dialog output) — not a merge onto the existing rule.
3. **Backend update** (`data_contracts_manager.py:2658-2673`) deletes existing
   `DataQualityCheckDb` rows for the object and re-creates them from the payload
   via `_create_quality_checks`, which *does* read `implementation`/`engine`/
   `mustBe*` (1995–2004) — but they're not in the payload.

⇒ **Editing + saving any quality rule via the dialog silently sets
`implementation`, `engine`, and all `must_be*` to NULL**, disabling the executable
check while the cosmetic `rule` text survives. The rule still renders as defined.

**Asymmetry:** ODCS import preserves the executable fields (seeded rules run);
only the dialog round-trip strips them. This is why the Enforce demo works on
seeded rules but a rule edited live on camera would not execute.

---

## C. Column / schema-level rules — modeled, imported, not authorable

- **Modeled.** `DataQualityCheckDb.level` ∈ {`contract`, `object`, `property`}.
  ODCS property-level quality is imported per-property
  (`data_contracts_manager.py:1162-1169`, `1267-1269`, reading
  `schema_obj.quality_checks`). The TS `QualityRule` type and the per-property
  `quality` field both exist.
- **Not authorable / not targetable in the UI.** The details view shows a single
  contract-wide **Quality Rules** list bound to `contract.qualityRules`
  (`data-contract-details.tsx:2789+`). The dialog offers a `level` dropdown that
  includes `property`, but there is **no control to bind the rule to a specific
  column**. Worse, `_create_quality_checks` attaches every UI-created rule to the
  **first** schema object (`data_contracts_manager.py:1966`), not to a property.

⇒ Property-level rules round-trip correctly **from ODCS import**, but you cannot
create or target a per-column rule through the UI today.

---

## UX recommendations (in priority order)

1. **Fix the strip-on-edit bug first** (small, high-value, demo-relevant). Two
   options; prefer (b):
   - (a) Make the dialog carry `implementation`/`engine`/`mustBe*` through hidden
     state and submit them unchanged on edit.
   - (b) Make the update path **merge by `stable_id`** (or array index) onto the
     existing check instead of delete-and-recreate, so any field the dialog
     doesn't know about is preserved. Safer and future-proofs against the next
     hidden field.

2. **Make the visible field the executable field.** Replace the free-text
   "Rule Expression" with a small **guided builder** for the common DQX checks —
   not-null, regex/`rlike`, range (via `mustBe*`), enum/`isin`, uniqueness — that
   emits a correct `implementation` and sets `engine`. Keep a **"custom SQL
   expression"** escape hatch, clearly labelled *"this is the SQL DQX runs,"*
   ideally with a validate/preview against sample data. The goal: the thing you
   see is the thing that runs.

3. **Surface and target column-level rules.** In `schema-property-editor.tsx`,
   allow attaching a rule to that property (bind `object_id` + property) and show
   per-column rules inline. The model and import already support it; only
   authoring is missing.

4. **Label the metadata fields.** Add helptext distinguishing what is
   documentation (`dimension`, `business_impact`) from what drives execution
   (`implementation`/`engine`) and criticality (`severity` → DQX `criticality`).

### Demo implications
- The Enforce demo runs on **seeded** rules, which carry `implementation`. Do not
  add or edit quality rules via the dialog on camera — the edited rule won't
  execute. Pre-seed everything.
- Narrate DQX as reading the contract's `implementation`/check spec, not the
  displayed expression.

---

## Key references

- `src/backend/src/db_models/data_contracts.py` — `DataQualityCheckDb` columns.
- `src/backend/src/controller/data_contracts_manager.py`
  - `_create_quality_checks` (1956) — reads `implementation`/`engine`/`mustBe*` (1995–2004); attaches to first object (1966).
  - update path delete-and-recreate (2658–2673).
  - property-level import (1162–1169, 1267–1269).
- `src/frontend/src/components/data-contracts/quality-rule-form-dialog.tsx` — dialog fields (28–48, 71–79).
- `src/frontend/src/views/data-contract-details.tsx` — edit handler (1140–1143), quality list (2789+).
- `src/frontend/src/types/data-contract.ts` — `QualityRule` incl. `engine`/`implementation`/`mustBe*` (213–226).
