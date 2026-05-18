# DAIS 2026 "Safe Skies" Demo Plan

**Talk:** *Safe Skies: Automating Trust at Scale with AI-Generated Data Contracts*
**Presenters:** Michael Hewitt (Solution Architect, Boeing) + Alan Reese (Resident Solutions Architect, Databricks)
**Venue:** Data + AI Summit · June 2026
**Duration:** 40 minutes
**Track:** Governance and Security
**Source materials:** [Drive folder](https://drive.google.com/drive/folders/1pgEtC2JdB8BpDknmMslcRcrWi1lHJ_zf) — talk outline + slide spec + .pptx

## Goal of this plan

Build an instance of Ontos centered on aviation flight operations, then capture **six pre-recorded demo videos** (~15.5 min total, ~39% of the 40-min talk) against it:

| Demo | Length | Story |
|---|---|---|
| 1. Contract Authoring (two tables) | ~5 min | AI profiles two raw tables (OAG schedule + ADS-B telemetry) → infers semantic types (ICAO, IATA, lat/lon, PII) → drafts ODCS YAML → asks tailored augmentation questions → human approves in Ontos. Two tables defuses "you cherry-picked the dataset" pushback. |
| 2. Discovery + Marketplace | ~2 min | Business user searches for "Global Flight Ops" (not `table_adsb_v2`); product card surfaces Certified · Contract version · Owning domain · Last quality check; Consumer subscribes |
| 3. DQX Quarantine | ~2 min | DQX consumes the Ontos contract natively, routes bad rows (negative altitude, malformed ICAO) to a quarantine table |
| 4. Notification fires | ~2 min | Contract violation in Demo 3 fires notifications to the owner AND every subscriber via Ontos's NotificationsManager. Strongest "trust is engineered" beat. |
| 5. Genie with trust signals | ~2 min | Business user queries the Genie space; answer cites the certified contract, shows trust badges. Replaces slide 22's mocked screenshot. |
| 6. Lakehouse Monitor drift | ~2.5 min | Real LH Monitor; flight volume drops 40%; alert fires; links back to contract/owner in Ontos. Replaces slide 21's mocked screenshot. |

Live-vs-recorded decision deferred until videos are in hand.

## Key decisions locked in

| Decision | Choice |
|---|---|
| Deployment | Local-iterate against remote state; redeploy via `databricks bundle deploy` to the existing `ontos` Databricks App. Full wipe-and-rebuild OK. |
| Workspace | `adb-4279470166116430.10.azuredatabricks.net` (Databricks profile `areese`) |
| App URL | `https://ontos-4279470166116430.10.azure.databricksapps.com` |
| Lakebase instance | `ontosdb` / db `databricks_postgres` / schema `app_ontos` |
| SQL warehouse | `6b017b77fb6a5df9` (Serverless Starter Warehouse) |
| LLM endpoint | `databricks-claude-sonnet-4-5` (already wired to the deployed app) |
| Volume | `areese_demo_catalog.ontos.ontos_volume` |
| Demo data catalog | **New `safe_skies` catalog** (created) with per-domain schemas: `flight_ops`, `maintenance`, `crew`, `scheduling`, `regulatory`, `fuel`, `passenger` |
| Data realism | Pure synthetic via Polars + Mimesis; OurAirports CSV for ICAO/IATA realism |
| Domain depth | Flight Ops deep; neighbor domains as breadcrumbs (8–12 real products + 30–50 stubs for marketplace density) |
| Cross-tool scope | End-to-end: Ontos + DQX pipeline + real Genie space + real Lakehouse Monitor. **No mocking.** |
| Recording deadline | **Code-complete by 2026-05-31** (~2 weeks from start). Most of it by end of week 1 (~2026-05-22). |
| Ontos Labs status | Lives at `github.com/databrickslabs/ontos` (confirmed; slide 24 is correct) |

## Narrative recommendations (separate from build)

1. **Add subscribe → violate → notify beat** — Ontos's built-in subscription + notifications loop is the strongest demo of "trust is engineered, not assumed." Demo 2 records the subscribe action; Demo 3 records the notification firing in the subscriber's inbox.
2. **Position Ontos as substrate, not as one of the Four Moves** — Ontos is the home for *Standardize*, the interface for *Generate*, the consumer of *Enforce* results, and the engine of *Discover*. That's a sharper claim than "Ontos is the discovery layer."
3. **Trim the sidebar for demo personas** — Hide MDM, Catalog Commander, Security Features, Compliance, Entitlements from the Consumer + Producer personas used in recording. Off-topic features distract audience attention during demos.
4. **Pin the LLM seed/temperature** in Demo 1 — re-cutting the video should be reproducible. Cache profile + LLM outputs for the demoed table so the recording is deterministic.
5. **Stub 30–50 marketplace products** — Slide 6 says "hundreds of data products". Marketplace search results need visual backing for that claim. Stubs are titles + domains only; never clicked.
6. **Live-app fallback for Q&A** — Pre-recorded videos are primary, but the deployed app should be working live as cheap insurance against the inevitable demo question.
7. **Make the human edit the contract before publishing in Demo 1** — Don't let the demo script "AI drafts → click approve" path through. Show 1–2 substantive edits so the "AI removes the blank page, humans approve" line is credible.

## Architecture — the four moves and where Ontos sits

```
Standardize          Generate              Enforce          Discover
────────────         ────────              ────────         ────────
ODCS v3.1     ────►  LLM-assisted   ────►  DQX (reads      ─────►  Ontos
ODPS                  drafting in           ODCS natively)          marketplace
                      Ontos                                          + ontology
   │                     │                     │                       │
   └──────── Ontos as substrate (Lakebase Postgres + UC) ──────────────┘

                        Unity Catalog
                        Lakehouse Monitoring (drift)
                        AI/BI Genie (consumption)
```

## Phase plan

### Phase 0 — Bootstrap workspace + local-remote dev wiring  *(in progress)*
- [x] Authenticate Databricks CLI profile `areese`
- [x] Audit deployed Ontos app — running, last deployed 2026-01-21
- [x] Identify warehouse, Lakebase, LLM endpoint, Volume
- [x] Create `safe_skies` catalog
- [ ] Create seven domain schemas under `safe_skies`
- [ ] Create `.env.dev` for local-against-remote-state
- [ ] Boot uvicorn + Vite locally; smoke-test against remote Lakebase

### Phase 1 — Aviation synthetic data + UC bronze
Polars + Mimesis generator producing a coherent flight-day across:
- ADS-B telemetry (per-second tracks)
- OAG-style schedule
- Airports w/ ICAO + IATA (OurAirports CSV)
- Airlines, aircraft registry
- METAR weather
- ATC events
- Stubs: maintenance work orders, crew rosters, fuel uplifts, passenger PNR aggregates

Include intentionally-dirty rows tagged for Demo 3 (negative altitude, malformed ICAO).

### Phase 1b — `demo_data_aviation.sql` metadata preset
Seed the Ontos metadata side:
- Aviation domain hierarchy
- Teams (Flight Ops Platform, Operations Analytics, Schedule Planning, etc.)
- ~8–12 data products with draft/published contracts
- Owning domains, certification metadata, quality items

Plus the 30–50 stub products from recommendation #5.

### Phase 2a — Backend AI contract generation pipeline
1. **Profile** UC table — sample rows, type/null/distinct, distributions, candidate keys
2. **Infer semantic types** via Claude Sonnet 4.5 — ICAO/IATA codes, ISO8601, lat/lon, currency, PII
3. **Generate augmentation questions** tailored to profile gaps (LLM-suggested, ~4–6)
4. **Draft ODCS v3.1 YAML** from profile + answers
5. **Validate** against `odcs-json-schema-v3.1.0.json`

Reuse `llm_service.py` and `schema_import_manager.py`. Add unit tests on prompt outputs.

### Phase 2b — Contract authoring wizard UI
Multi-step wizard: table picker → profile preview → augmentation Q&A side panel → ODCS YAML preview with diff/edit → approve + publish. Inferred semantic types as colored column badges (per slide spec: *the single most differentiating visual*).

### Phase 3 — Marketplace + ontology polish
Wire `table_adsb_v2` + `table_oag_clean` + weather + ATC → logical DataProduct **"Global Flight Ops"** via `EntityRelationshipDb`. Confirm trust signals (Certified · Contract version · Owning domain · Last quality check). Tune search.

### Phase 3b — Subscribe → violate → notify closed-loop beat
Verify consumer subscription end-to-end. Verify NotificationsManager fires to both owner and all subscribers on DQX rejection. Build the linkage if missing.

### Phase 3c — Trim sidebar + stub products
Configure feature access on the Consumer + Producer personas to hide off-topic features. Seed 30–50 marketplace stub products across domains.

### Phase 4a — Wire DQX to read Ontos contracts natively
DQX v0.11+ consumes ODCS natively — no compiler needed (corrected per Alan). What's needed:
1. Every published Ontos contract exportable as ODCS YAML at a stable UC Volume path
2. "Run DQX validation" action on contract detail → triggers a Databricks job
3. Job results write back to `QualityItemDb` so marketplace card reflects pass/fail counts

### Phase 4b — DQX quarantine pipeline
Databricks job: bronze → DQX rules from contract → silver/quarantine → gold. Mix pre-seeded dirty rows. Wire results to Ontos.

### Phase 5a — Genie space + GenieSpacesManager
Activate the partial Genie infra. Build missing `genie_spaces_manager.py`. Create real Genie space backed by "Global Flight Ops" gold tables. Push trust signals as Genie space metadata.

### Phase 5b — Real Lakehouse Monitor + drift alert
TimeSeries monitor on a gold flight-volume table. Drift threshold + Slack/email alert. Test the "Flight volume dropped 40% in last hour" scenario fires.

### Phase 6 — Deploy + smoke test
`databricks bundle deploy` to the existing Databricks App. Smoke-test all three demo flows on the deployed app. Pre-rehearse against 3+2+2 minute video budget.

### Phase 6b — Record six demo videos
Six demos against deployed app, ~15.5 min total:
- Demo 1: AI contract gen on OAG + ADS-B (~5 min)
- Demo 2: Marketplace + Consumer subscribe (~2 min)
- Demo 3: DQX quarantine (~2 min)
- Demo 4: Notification fires to owner + subscribers (~2 min)
- Demo 5: Genie with live trust signals (~2 min)
- Demo 6: Lakehouse Monitor drift alert (~2.5 min)

"Synthetic flight telemetry" caption-bug for first 3s of each. Coordinate narration with Michael.

**Slide spec patches needed** (to be drafted for Michael):
- Slide 21: "Mocked screenshot" → "Pre-recorded video, ~2.5 min"
- Slide 22: "Mocked screenshot" → "Pre-recorded video, ~2 min"
- Insert new slide between 17 and 18 for Demo 4 (Notification loop), OR fold into expanded Demo 2 narration
- Slide 16 video timer: ~3 min → ~5 min (two-table demo)

## Timeline

| Date | Milestone |
|---|---|
| 2026-05-17 | Plan locked; Phase 0 in progress |
| ~2026-05-22 | End of week 1 — Phases 0, 1, 1b done; Phase 2a/2b underway; Phase 3 starting |
| ~2026-05-29 | End of week 2 — Phases 2a/2b/3/3b/3c/4a done; 4b/5a/5b in flight |
| **2026-05-31** | **Code-complete; deployed; smoke-tested** |
| Week of 2026-06-01 | Record videos with Michael; deck integration; dry runs |
| ~mid-June 2026 | DAIS 2026 |

## Open questions

- DAIS exact session date (back-plan from this if internal review milestones)
- Boeing internal review milestones, if any
- Final closer line on slide 27 (placeholder per slide spec)

## Risks

| Risk | Mitigation |
|---|---|
| Phase 2 (AI contract gen) is biggest new build | Start immediately; pin LLM seed/temp; deterministic demo path |
| LLM output variance breaks reproducibility | Cache the demo table's profile + LLM outputs; record video against cached version |
| DQX integration surprises | Read DQX v0.11+ ODCS support docs first; smoke test on day 1 of Phase 4 |
| Genie space API quirks | Phase 5a starts only after Phase 4 stable; Lakehouse Monitor is well-trodden |
| Workspace permissions | Confirmed `safe_skies` catalog created; warehouse + LLM + Lakebase all reachable |
| Pre-recorded demo loses live-app credibility | Keep deployed app live for Q&A as fallback |

## Reference

- Outline: [Data and AI Summit Talk Outline](https://docs.google.com/document/d/1fCm62zrVdvvv7pYtrmTZHBhWB9K-x9WDmt4EDjVLBkE)
- Slides: [Safe Skies — DAIS 2026 Slide Spec](https://docs.google.com/document/d/1kKzuyPP2whvhKd7_Xai05RMsF131JHj4_hQ_xN4ZPoI)
- Template .pptx: [Presentation.pptx](https://docs.google.com/presentation/d/1g2Fto_u4odt0O688xuTd-uWUhUxWR_-4)
- Ontos repo: github.com/databrickslabs/ontos
- ODCS schema: `src/backend/src/schemas/odcs-json-schema-v3.1.0.json`
- BITOL ODCS: https://github.com/bitol-io/open-data-contract-standard
- BITOL ODPS: https://github.com/bitol-io/open-data-product-standard
- DQX repo: github.com/databrickslabs/dqx
