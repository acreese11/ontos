# Demo 4 (Maintain) — Keeping Trust Honest as the Mesh Scales

> **Deck slides 20–21** (deck's internal labels: "Demo 4 — The Trust Loop Closes" +
> "Drift Catches What Row-Level Checks Cannot"). The **Maintain** move in the
> lifecycle. **Slot: ~5:00** = live narration over a video + verbal coverage of the
> narrated beat.
> **Narration: Michael owns it** (deck agenda "Demo: Maintain — Michael — 5 min");
> Alan interjects on the rule/drift mechanics and closing-the-loop ([Alan] brief beats).

Authoring and enforcing *one* contract is the easy part; maintaining trust across a
*growing* federated mesh is the real job. Four beats — three runnable today, one narrated:

1. **Compliance — Contract Coverage** — ✅ **BUILT + validated.** Is every table governed by
   exactly one contract? The macro view of the governance landscape.
2. **Drift detection** (schema/metadata) — ✅ **BUILT (PR #33).** The contract said the table
   has *these* columns and types; does the *live* Unity Catalog table still match? Catches a
   column added/dropped, a type changed (`int → bigint`), a nullability flip. Runs in-app,
   on demand. App. B.
3. **Notification loop** (deck slide 20) — ✅ **BUILT.** When governance breaks — a DQX quality
   failure **or** a schema-drift finding — the owner + every subscriber are notified
   automatically. *The talk's emotional peak — the trust loop closes.* App. A.
4. **Lakehouse Monitoring** (statistical drift, deck slide 21) — ⚠️ **narrated** (Databricks-UI
   path live; full Ontos integration is a stretch goal). Catches what row-level *and* schema
   checks cannot — "flight volume dropped 40% in the last hour." App. C.

**The point:** trust isn't asserted once at authoring — it's *maintained* by rules that run
continuously. Coverage proves the landscape; drift detection proves each contract still holds;
the notification loop tells the people who care; Lakehouse watches the statistical envelope.

**The arc:** macro coverage → micro drift on one contract → the loop that tells everyone → the
statistical safety net. Beats 2 and 3 connect — a drift finding *fires* the loop in beat 3.

---

## Timing budget (~5:00 slot)

| Beat | Who | Target |
|---|---|---|
| 0 · Frame Maintain + callback to lifecycle slide | Michael | 0:25 |
| 1 · Compliance: run Contract Coverage → 50% + read the gaps | Michael (Alan: how the rule works) | 1:05 |
| 2 · Drift detection: contract vs live `adsb_v2` → schema drift | Michael (Alan: contract-as-spec mechanic) | 1:15 |
| 3 · Notification loop: drift/DQX failure → owner + subscriber told (slide 20) | Michael (Alan: arch) | 1:25 |
| 4 · Lakehouse Monitoring: the statistical layer (slide 21) | Michael | 0:35 |
| 5 · Button: the safety net under the whole lifecycle | Michael | 0:15 |

> **Realism:** Beats **1, 2, 3 are all built and recordable today** — Coverage (compliance),
> schema-drift detection (PR #33), and the trust loop. Beat 4 (Lakehouse) is the only narrated
> one and is now a brief *capstone*, not the centerpiece, because schema-drift carries the
> "drift catches what rows can't" point with a live build. The slot fills with substance.

---

## Talk track

**Beat 0 — Frame** · *[DO] flash the lifecycle slide, finger on **05 · Maintain**.*
- **[SAY · Michael]** "Authoring and enforcing one contract is the easy part. Maintaining trust
  across a *growing* mesh — that's the real job. Three questions: is everything governed, does
  each contract still hold, and when something breaks, who finds out?"
- **[Alan, brief]** "And none of those you answer by hand across hundreds of tables — you answer
  them with rules that run."

**Beat 1 — Compliance / Coverage** · *[DO] Compliance → Contract Coverage → Run (pre-warmed); then open the failing tables.*
- **[SEE]** the run completes: a **coverage score + per-table pass/fail**; then the gap list.
- **[SAY · Michael]** "This walks the whole `safe_skies` catalog and checks every table has
  exactly one contract. We're at **50%** — 13 governed, 13 not." **[Alan, brief]** "One rule —
  `contract_count = 1` — and it catches both failure modes: zero contracts, or two conflicting."
- **[SEE]** the ungoverned tables — `adsb_v2_raw`, `oag_schedule_raw`, the `*_raw`/`*_quarantine`
  landing tables. **[SAY · Michael]** "`adsb_v2_raw` is the exact table we drafted a contract
  for in the Author demo — coverage is how you *find* the gap; Author is how you close it."

**Beat 2 — Drift detection** · *[DO] open the **live_flights** contract (`safe_skies.flight_ops.adsb_v2`) → Source Conformance panel → Run.*
- **[SAY · Michael]** "Coverage tells you a table *has* a contract. It doesn't tell you the table
  still *matches* it. Schemas drift — someone widens a column, adds a field, drops one. So we
  validate the contract's declared schema against the *live* Unity Catalog table."
- **[SEE]** the panel returns drift findings — e.g. **`alt_baro_ft` type `integer → bigint`**, a
  **new column present in the table but not the contract**, a **dropped column**. Each finding
  names the column and the exact change.
- **[SAY · Michael]** "This is the failure DQX can't see. DQX checks the *rows* — is the altitude
  non-negative. This checks the *shape* — did the table stop matching the promise. Same table
  from the Enforce demo, a different class of break." **[Alan, brief]** "And it's the contract itself
  doing the checking — the declared schema is the spec; the live table is the implementation."

**Beat 3 — Notification loop** · *deck slide 20 (✅ built — live or pre-recorded; see App. A).*
- **[DO]** The drift finding from Beat 2 (or a DQX failure) fans out. **[SEE]** the **owner's**
  Ontos inbox lights up; **[SEE]** the **subscriber's** inbox (the consumer who subscribed in
  Discover) gets the same notification — within seconds. Click through → lands on the contract.
- **[SAY · Michael]** "Coverage finds gaps, drift finds breaks — but neither matters unless the
  right people hear about it. When governance breaks, whether it's a DQX rule or a schema drift,
  the owning team **and every subscriber** are notified, automatically — the consumer never has to
  chase the producer." **[Alan, brief]** "Same trust loop, two triggers: that subscription from
  Discover is the registration; the notification is Ontos closing the loop federation opened."

**Beat 4 — Lakehouse Monitoring** · *deck slide 21 (narrate; ⚠️ Databricks-UI path — see App. C).*
- **[SAY · Michael]** "There's one more layer. Row-level checks and schema checks both miss that
  *yesterday's* volume was normal and *today's* is down 40%. That's statistical drift — Lakehouse
  Monitoring catches it." **[Alan, brief]** "And the next step is mapping those monitor results
  back to the SLA properties in the contract, so freshness and volume live in the same place as
  the schema — that's the integration we're building toward."

**Beat 5 — Button** · *Michael.*
- **[SAY · Michael]** "Author, enforce, discover — with coverage, drift detection, notifications,
  and monitoring watching the whole thing. That's operating contracts at scale, not just writing
  one. Governance is a product, not a project."

---

## Run setups (do once before recording)

### Beat 1 — Contract Coverage (compliance)

| Thing | Value |
|---|---|
| Persona | Producer / Governance (Compliance is a govern-stage feature) |
| Policy | **"Contract Coverage"** (id `513e36e9-…`; seeded on a fresh load) |
| Scope | catalog `safe_skies`, `information_schema` excluded |
| Verified result | 26 tables → **13 governed / 13 ungoverned = 50.0%** |

1. Confirm the **Contract Coverage** policy exists (Compliance → Policies). On an older DB,
   create it under **New Policy** with the rule in App. A-of-old / the coverage assert
   (`ASSERT t.contract_count = 1`).
2. **Pre-run once** so the score + per-table results are warm; the on-camera run reproduces it.
3. Have the **failing-tables view** ready to cut to (the gap is the story).

### Beat 2 — Drift detection (schema/metadata)

| Thing | Value |
|---|---|
| Persona | Producer / Governance (Data Contracts READ_WRITE) |
| Contract | **live_flights** → `safe_skies.flight_ops.adsb_v2` |
| Surface | Contract details → **Source Conformance** panel → **Run** |
| Endpoint | `POST /api/data-contracts/{id}/validate-source` (OBO live read) |

**Staging the drift (so a clean seed actually shows findings).** A freshly generated `adsb_v2`
matches its contract, so a live run on a pristine seed will pass. To make drift appear on camera,
introduce one *before* recording — pick the most legible:

```sql
-- Type drift: contract declares alt_baro_ft INTEGER; widen the live column.
ALTER TABLE safe_skies.flight_ops.adsb_v2 ALTER COLUMN alt_baro_ft TYPE BIGINT;  -- or DOUBLE
-- Extra column: present in the table, absent from the contract.
ALTER TABLE safe_skies.flight_ops.adsb_v2 ADD COLUMN ingest_batch_id STRING;
-- Missing column: drop one the contract still declares (most dramatic; reversible).
-- ALTER TABLE safe_skies.flight_ops.adsb_v2 DROP COLUMN alt_geo_ft;
```

- The **`int → bigint`** case is the one to lead with: it's the most common real-world drift and
  exactly what the validator was hardened to catch (PR #33 review — substring matching used to
  let it pass silently).
- **Reset:** re-generate the table (re-load aviation seed) or reverse the `ALTER`s.
- **Pre-run once** so the panel renders fast on camera; the on-camera run reproduces the findings.

### Beat 3 — Notification loop

See **Appendix A** — the manual end-to-end validation recipe (run before recording). Note the
**local-auth caveat**: the two-inbox *visual* needs a deployed app with two sign-ins.

---

## Gotchas
- **Drift on a clean seed shows nothing** — you must stage drift first (recipe above). Don't run
  it live on a pristine table expecting findings.
- **Drift → notification on the *same* subscribed contract:** the seeded subscriber
  (`consumer@safe-skies.demo`) is on the **🎯 Global Flight Ops** product. For the drift finding
  in Beat 2 to light up a *subscriber* inbox (not just the owner) on the same contract, either
  run drift on the contract that product's output port links to, **or** also subscribe the
  consumer to the `live_flights`/adsb product. Otherwise show drift on `adsb_v2` (owner notified)
  and the two-inbox visual on Global Flight Ops (App. A). *(Staging item — pick one pre-talk.)*
- **Conflict case isn't in the seed:** after dedup there are **0** double-governed tables, so a
  live coverage run shows the *ungoverned* (`0`) case only. Stage one (below) or narrate it.
- Coverage + drift both walk the catalog via the warehouse — pre-run so they're warm.
- Coverage scope is hard-coded to `safe_skies` in the rule; a different catalog needs the rule edited.

## Staging the conflict case (Beat 1, optional — to show both coverage failure modes live)
1. Author a second draft contract whose schema references an *already-governed* table (one of
   the 13 passing) — via the Author flow or a quick draft.
2. Re-run Contract Coverage → that table now fails `…has 2 contract(s) (expected exactly 1)`.
3. Reset: delete the staged contract and re-run (or re-seed).
*(Not yet live-validated — the `>1` branch is logically covered by the same `= 1` assert.)*

## Reset between takes
- **Coverage** is read-only + idempotent — re-run freely; stable on the same data.
- **Drift** persists a validation run per execution; re-running is fine (latest run shown). Reset
  the *staged* drift (reverse the `ALTER`s / re-seed) only when you want a clean pass.
- **Notifications** — mark read / clear; re-seed to reset subscriptions.

---

## Status

| Beat | Source | Build status |
|------|--------|--------------|
| 1 · Compliance / Contract Coverage | (this file) | ✅ **Built + merged** — PR #16 + PR #18 (information_schema fix). Re-validated live 2026-06-15: 26 tables, 13/13, **50.0%** |
| 2 · Drift detection (schema/metadata) | (this file) | ✅ **Built** — `ContractValidationManager` + `POST /validate-source` + Source Conformance panel (**PR #33**). Detects missing/extra column, type change (incl. `int→bigint`), nullability flip; fires the trust loop on findings. 17 unit tests. **Stage drift + live-validate before recording.** |
| 3 · Notification loop | demo-4 | ✅ **Built** — `QualityManager.create()` (DQX path) **and** `ContractValidationManager._notify_drift` (drift path) fan a failure out to owner + subscribers via `NotificationsManager`. Tests in `test_quality_trust_loop.py` + `test_contract_source_validation.py`. Manual e2e recipe in App. A. |
| 4 · Lakehouse Monitoring (statistical drift) | demo-6 | ⚠️ **Narrated** — Databricks-UI path can be shown live; full Ontos integration (monitor results → contract SLA properties) is a **stretch goal**. App. C. |

Three of four beats run today; Lakehouse is the only narrated layer and is now a brief capstone.

---

## Trust-loop placement & cross-demo 5-min plan

**The trust loop spans two demos — by design.**
- **Subscribe happens in Discover** (demo 3, Michael): the consumer finds *Global Flight Ops*,
  inspects the contract, and **subscribes → registers for violation notifications.**
- **Loop *closure* happens here in Maintain** (Beat 3): a DQX violation **or a schema-drift
  finding** fires → the owner **and that same subscriber from Discover** are notified → "the
  consumer didn't have to ask if the data broke; they were told."

**Keep them apart on purpose.** Discover = *find & trust*; Maintain = *operate & watch over
time*. The gap between subscribing and being alerted mirrors real life. Do **not** collapse the
notification into the end of Discover.

**Mechanical dependency:** the identity that subscribes in Discover must be the same inbox that
lights up here. (demo-3 already flags "use the same consumer identity.")

**The technique that fills 5 min with substance (not padding) = cross-demo threading:**
- Discover→Maintain: "you'll see this subscription fire in a moment."
- Maintain→Discover: "remember the consumer who subscribed in the marketplace."
- Maintain→Author: Coverage flags `adsb_v2_raw` as *uncontracted* — the exact table the Author
  demo drafts a contract for; and drift checks `adsb_v2`, the *silver* table that demo produces.
  Closes Author→Maintain on the same lineage.
- Maintain internal: the drift finding in Beat 2 *is* the trigger shown in Beat 3 — one continuous
  thread, not two disconnected features.

## Open items (re Maintain + Discovery)

1. **Notification loop (Beat 3)** — ✅ **built**, now on **two triggers** (DQX + drift). Remaining:
   **live-validate it's recordable end-to-end locally** (App. A recipe) and pin identity
   continuity (item #4).
2. **Drift detection (Beat 2)** — ✅ **built** (PR #33). Remaining: **stage the drift + live-record**
   the Source Conformance panel on `adsb_v2`; decide the drift→subscriber wiring (Gotchas).
3. **Drift → subscriber notification continuity** — wire the seeded subscriber to the contract
   whose drift you demo (Gotchas), so Beat 2 → Beat 3 is one contract, not two.
4. **Identity continuity** — pin the same consumer identity across demo-3 subscribe and the Beat-3
   notification; bake into both run-setups.
5. **Conflict-case staging** (double-governed table) — Beat-1 refinement worth deciding pre-talk.
6. **Lakehouse stretch** — full integration mapping monitor results → contract SLA properties
   (`data_contract_sla_properties`: freshness/volume/etc.). App. C.
7. **→ demo-3 (Discover):** scope **using "Ask Ontos" for *discovery*** into the Discovery demo
   (per Alan, 2026-06-15). *(Action lives in `demo-3-discover-marketplace-subscribe.md`.)*

---

# Appendix A — Notification loop (✅ built)

> The **Enforce/Drift → Discover** join. Co-narrated: **Alan** = subscriptions as a contract
> trust pattern, **Michael** = operational impact ("a consumer never has to chase the producer").

**Readiness: ✅ BUILT.** The closed loop exists end-to-end, now on **two triggers**:
- **DQX path:** `QualityManager.create()` calls `notify_quality_failure()` whenever a recorded
  quality item for a **`data_contract`** represents a failure (`checks_passed < checks_total`, or
  — when counts are absent — `score_percent < 100`).
- **Drift path (PR #33):** `ContractValidationManager._notify_drift()` fires on any schema-drift
  finding from a source-conformance run.
- **Both** resolve recipients via `QualityManager.resolve_failure_recipients()`: the contract
  **owner** (ODCS team member with `role == "owner"`) **plus** every **subscriber** of any product
  whose output port links to the contract (`DataProductsManager.get_products_by_contract` →
  `EntitySubscriptionsManager.get_subscribers(entity_type="DataProduct")`). De-duplicated, owner first.
- Notifications fire through the existing `NotificationsManager.create_notification` — **no new
  notification system.** DQX payload: title `Quality failure: {contract}`. Drift payload: title
  `Schema drift: {contract}`, subtitle the drift summary, deep link `/data-contracts/{id}`.
- A subscriber is seeded: the aviation seed subscribes `consumer@safe-skies.demo` to **🎯 Global
  Flight Ops** (the Discover-demo consumer identity). The contract owner
  (`operations-analytics-lead@safe-skies.demo`) is notified via the contract's ODCS owner team member.

**Architecture note:** the trigger lives at the *observation* boundary (quality-recording, or
source-validation), not inside DQX or UC. Any enforcement source that writes a failing quality
item, and any drift run, fans out the same loop — Ontos observes the result, it doesn't own the
engine. Failures here never break the underlying operation: the quality/validation row is committed
first, and any notification error is logged and swallowed.

## Timing budget (~2:00 — within Beat 3)
| Sub-beat | Target |
|---|---|
| Recap: the subscriber from Discover (Alan) | 0:20 |
| The trigger fires — drift finding (Beat 2) or a DQX failure | 0:30 |
| Owner's Ontos inbox receives the notification | 0:25 |
| Subscriber's inbox receives it too — within seconds | 0:25 |
| Notification detail: what broke + one-click link to contract | 0:15 |

## Manual end-to-end validation recipe (run before recording)

Goal: fire a real failure against the `global_flight_ops` contract and watch the notification land
in **both** the owner's and the subscriber's Ontos inbox. Three ways to trigger — a schema-drift
run, a real DQX run, or a direct quality-item POST. All end in the same fan-out.

**Prereqs**
1. Load the aviation seed (Settings → Demo Data → Load Aviation, or
   `POST /api/settings/demo-data/load-aviation`). Seeds the `global_flight_ops` contract (owner
   `operations-analytics-lead@safe-skies.demo`), the **🎯 Global Flight Ops** product, and the
   subscriber **`consumer@safe-skies.demo`**.
2. Note the contract id: Data Contracts → *global_flight_ops* → copy from the URL, or
   `GET /api/data-contracts?search=global_flight_ops`.

**Path A — schema-drift run (Beat 2 → Beat 3, the integrated path)**
3a. Stage drift on the contract's mapped table (Beat 2 staging recipe), then
    `POST /api/data-contracts/$CONTRACT_ID/validate-source`. Any finding fires `_notify_drift`.
    *(Requires the subscriber to be on the drifted contract — see Gotchas.)*

**Path B — real DQX run (the classic Enforce path)**
3b. Run the DQX/quality enforcement job that emits a failing `QualityItem` for the contract
    (`source="dqx"`, `entity_type="data_contract"`, `checks_passed < checks_total`).

**Path C — direct POST (fast loop, no cluster)**
3c. POST a failing quality item (requires READ_WRITE on `data-domains`):
    ```bash
    curl -X POST \
      "$ONTOS/api/entities/data_contract/$CONTRACT_ID/quality-items" \
      -H "Content-Type: application/json" \
      -d '{
            "entity_id": "'"$CONTRACT_ID"'",
            "entity_type": "data_contract",
            "title": "not_null_check",
            "dimension": "completeness",
            "source": "dqx",
            "score_percent": 80,
            "checks_passed": 4,
            "checks_total": 5
          }'
    ```

**Verify (all paths)**
4. **Owner notification** for `operations-analytics-lead@safe-skies.demo`.
5. **Subscriber notification** for `consumer@safe-skies.demo` (same notification).
6. **Deep link** points to `/data-contracts/{contract_id}`.
7. **Negative check (DQX/POST):** post with `checks_passed: 5, checks_total: 5, score_percent: 100`
   → **no** new notification (a passing run is a no-op).

> **Local-auth caveat — read before recording.** Local dev runs as a **single** user
> (`MOCK_USER_EMAIL`); there is **no in-UI user switching**, so you cannot *visually* show two
> separate inboxes locally. `NotificationsManager.get_notifications` filters per recipient.
> - **To verify the loop locally:** check the `notifications` table for rows with `recipient` =
>   both emails — that confirms the fan-out fired.
> - **For the two-inbox *visual*** (the demo's payoff): record on a **deployed app** where you can
>   sign in as each identity, owner session beside subscriber session.

## Walkthrough (live or pre-recorded)
1. **[SAY · Alan]** "In Discover a consumer subscribed to Global Flight Ops. A subscription is a
   Data Contract trust pattern — Ontos implements it directly."
2. **[DO]** Trigger via the drift run from Beat 2 (Path A) or the quality-item POST (Path C).
   **[SAY · Alan]** "When a drift run — or a DQX failure — records a break against the contract…"
3. **[SEE]** The **owner's** Ontos inbox — a new notification: what broke + a link to the contract.
4. **[SEE]** The **subscriber's** inbox — the same notification, within seconds. **[SAY · Michael]**
   "The consumer never has to chase the producer or wonder if today's data is good. They're told."
5. **[DO]** Click the link → lands on the contract. **[SAY · Alan]** "Subscriptions plus
   notifications close the loop that federated ownership opens."

## Presentation fallback
- Pre-record the two-inbox fan-out using the recipe; the beat is built and deterministic.
- This is the strongest "trust is engineered, not assumed" moment in the talk — keep it, don't cut.

## Reset between takes
Mark notifications read / clear them; re-seed to reset subscriptions.

---

# Appendix B — Drift detection (✅ built, PR #33)

> The **schema/metadata** half of "drift." Co-narrated: **Alan** = the contract-as-spec mechanic,
> **Michael** = why shape-drift is the failure DQX can't see.

**Readiness: ✅ BUILT.** Inline source-conformance validation diffs a contract's *declared* schema
against the *live* Unity Catalog table and surfaces drift in the UI:
- **`ContractValidationManager`** (`controller/contract_validation_manager.py`): reads declared
  columns from `SchemaObjectDb`/`SchemaPropertyDb`, reads the live schema via
  `DatabricksConnector.get_asset_metadata(...).schema_info`, and diffs. Detects `missing_column`,
  `extra_column`, `type_change` (tolerant of parameterised forms like `decimal(10,2)`, but **not**
  `int`/`bigint` — that widening is caught), `nullability_change`.
- Persists a `DataContractValidationRun` + one `DataContractValidationResult` per finding
  (`check_type=schema_drift`). On any drift, fires the trust loop (App. A) — owner + subscribers.
- **API:** `POST /api/data-contracts/{id}/validate-source` (OBO live read),
  `GET /api/data-contracts/{id}/validation-runs` (latest run + results).
- **UI:** `SourceConformancePanel` on the contract details page — run-on-demand + per-finding results.
- **Tests:** 17 unit tests (`test_contract_source_validation.py`), incl. the int/bigint regression.

**The point:** DQX checks the *rows*; drift detection checks the *shape*. Same table from Enforce
(`adsb_v2`), a different class of break — and it's the contract itself acting as the spec.

## Timing budget (~1:15 — Beat 2)
| Sub-beat | Target |
|---|---|
| Coverage says "has a contract" ≠ "still matches it" (Alan) | 0:20 |
| Run Source Conformance on live_flights → findings | 0:30 |
| Read a finding: `alt_baro_ft int→bigint`, +extra column (Alan) | 0:15 |
| Why this is the failure DQX can't see (Michael) | 0:10 |

## Stretch (noted, not built)
Map drift findings to the contract's **SLA properties** alongside the Lakehouse statistical layer
(App. C) so schema + freshness + volume conformance read from one place.

## Reset between takes
Re-run freely (latest run is shown). Reset the *staged* drift (reverse the `ALTER`s / re-seed) to
return to a clean pass.

---

# Appendix C — Lakehouse Monitoring / statistical drift (⚠️ narrated, integration is a stretch)

> Originally **Slide 22** · the **statistical** drift beat. Co-narrated: **Michael** = operational
> framing, **Alan** = closing-the-loop / SLA-mapping callout.

**Readiness: ⚠️ NARRATED.** There is **no Lakehouse Monitor wiring inside Ontos** — no
monitor-create, no drift threshold, no alert-to-contract link. The **Databricks UI path** (create
a monitor, show a drift metric) *can* be demoed live in the workspace; what's missing is the Ontos
*integration* that ties a monitor alert back to the contract/domain.

**The distinction to draw on stage:** Beat 2 (schema drift) is the *shape* changing; this is the
*distribution* changing while the shape holds — "volume dropped 40%, freshness slipped." Both are
"drift"; only schema drift is built inside Ontos today.

**The point (if kept):** DQX catches row-level violations; schema-drift detection catches shape
changes; Lakehouse Monitoring catches statistical drift — and the vision is linking that alert back
to the contract + owning domain in Ontos.

## Timing / presentation recommendation
Keep this as a **~30–35s narrated capstone** over slide 21 (now that Beat 2 carries "drift catches
what rows can't" with a live build). Michael makes the statistical point; Alan names the stretch:
mapping monitor results → contract SLA properties.

## Stretch — full integration (the build, if it jumps the queue)
1. A **Lakehouse Monitor** (TimeSeries) on a gold flight-volume table in `safe_skies`.
2. A drift threshold + alert for "volume dropped 40% in an hour."
3. **Map monitor results back to `data_contract_sla_properties`** (freshness/volume/etc.) so SLA
   conformance lives beside schema conformance — the Beat 2 stretch and this one converge here.
4. A scripted data drop to make the alert fire on camera.

This is real Lakehouse Monitoring setup + a synthetic drop + the Ontos mapping — days, not hours.

## Walkthrough (target, only if built)
1. **[SAY · Michael]** "Row-level checks and schema checks both miss that *yesterday's* volume was
   normal and *today's* is 40% down. That's the harder failure."
2. **[SEE]** The Lakehouse Monitor on the gold flight-volume table (Databricks UI).
3. **[DO]** (Scripted) volume drops 40%. **[SEE]** Alert: "Flight volume dropped 40% in the last hour."
4. **[SAY · Alan]** "And the alert maps back to the contract's SLA properties and owning domain in
   Ontos — closing the loop is the point."

## Reset between takes
N/A until built (Databricks-UI path: reset the monitor's window / re-run the drop).
