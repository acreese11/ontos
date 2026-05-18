# Safe Skies — Domain · Product · Contract Model

**Companion to `dais-2026-safe-skies.md`.** This is the business model the synthetic data has to defensibly back. Designed contract-first so the demos land cleanly.

**Source-of-truth precedence:** This model takes priority over the slide spec's specific example table names (e.g., the slide spec's `table_adsb_v2` and `table_oag_clean` were placeholder examples). The talk reflects what real enterprise aviation data architectures look like — modeled against OAG and Cirium's published product taxonomies — and the slide spec will be updated to match this model where they diverge.

## The eight domains (slide 6's seven + Reference Data)

| # | Domain | Purpose | Owning team | UC schema |
|---|---|---|---|---|
| 1 | **Flight Ops** | Real-time and historical flight ops — what's airborne, what landed, what's late | Flight Ops Platform | `safe_skies.flight_ops` |
| 2 | **Scheduling** | Forward-looking schedule design, network changes, ATC flow | Network Planning | `safe_skies.scheduling` |
| 3 | **Maintenance** | Aircraft fitness, work orders, MEL/CDL | Engineering & Maintenance | `safe_skies.maintenance` |
| 4 | **Crew** | Crew rosters, duty-time tracking, qualifications | Crew Resources | `safe_skies.crew` |
| 5 | **Regulatory** | FAA/EASA/ICAO compliance reporting + safety logs | Regulatory Affairs | `safe_skies.regulatory` |
| 6 | **Fuel** | Fuel ops, hedging, settlement, SAF mix | Fuel Operations | `safe_skies.fuel` |
| 7 | **Passenger** | Bookings, loyalty, customer flows (PII-aware) | Commercial Analytics | `safe_skies.passenger` |
| 8 | **Reference Data** | Master/lookup data used by everyone (airports, airlines) | Data Platform | `safe_skies.reference` |

*(I'm adding a `reference` schema — common practice and lets us keep airports/airlines decoupled from any single business domain.)*

## Data product alignment (data-mesh-architecture.com taxonomy)

Each data product is classified by alignment — this drives ownership, composition, and how subscriptions/notifications propagate:

- **Source-aligned**: mirrors an operational system; owned by the source domain team. *("This is what's in our ADS-B feed.")*
- **Aggregate**: combines multiple source-aligned products into a unified view; owned by a specialized team. *("Global Flight Ops, the joined picture.")*
- **Consumer-aligned**: tailored to a specific stakeholder's analytical needs; owned by the consuming business team. *("On-Time Performance, the way Customer Comms wants it.")*

## Alignment is orthogonal to medallion layers

A common mistake: equating *source-aligned* with *bronze*. They're independent dimensions.

**Every data product — regardless of alignment — should have at least a silver layer.** The product team is responsible for curating their data: schema normalization, quality rules, possibly aggregations. The contract is for **what consumers see** (silver or gold), not for the raw landing zone.

- **Bronze** is the raw landing zone — typically *inside* a source-aligned product, not its output port. Often unitless of contracts.
- **Silver** is the contract-backed output of a product. Schema is normalized, quality rules are enforced. This is the minimum a product should publish.
- **Gold** is curated for specific analytical use. Aggregate and consumer-aligned products typically publish gold output ports.

In our model:

| Alignment | Internal layers | Output port (contract sits here) |
|---|---|---|
| Source-aligned | bronze + silver (+ optional gold) | silver (or gold if curated) |
| Aggregate | silver + gold (typically materialized from joined sources) | silver and/or gold |
| Consumer-aligned | gold (often a view on aggregate) | gold |

**The contract gates promotion between layers.** DQX takes the contract and rejects rows that don't comply, routing them to a quarantine table while clean rows promote to the next layer. The contract isn't a description — it's the *rule* that physically moves data between layers.

## The data products (real, with contracts)

Sixteen real products spanning all three alignments — plus 30+ stubs for marketplace density.

### Source-aligned (11) — operational reality

Each product has internal layers; the contract sits at the silver (or gold) layer. Tables in `safe_skies.<domain_schema>`:

| # | Product | Domain | Owner | Bronze → Silver → Gold | Contract on |
|---|---|---|---|---|---|
| 1 | **Live ADS-B Telemetry** | Flight Ops | Flight Ops Platform | `adsb_v2_raw` → `adsb_v2` | silver `adsb_v2` |
| 2 | **OAG Flight Schedules** | Scheduling | Schedule Data Ops | `oag_schedule_raw` → `oag_schedule` | silver `oag_schedule` |
| 3 | **Flight Status Events** | Flight Ops | Flight Ops Platform | `flight_status_raw` → `flight_status` | silver `flight_status` |
| 4 | **ATC Flow Initiatives** | Scheduling | Network Planning Ingest | `tmi_events_raw` → `tmi_events` · `notams_raw` → `notams` | silver `tmi_events` + silver `notams` |
| 5 | **METAR Observations** | Flight Ops | Operations Ingest | `metar_raw` → `metar_weather` | silver `metar_weather` |
| 6 | **Aviation Reference Master** | Reference Data | Data Platform | `airports`, `airlines`, `aircraft_registry` (silver only — vendor-curated) | silver tables |
| 7 | **Aircraft Maintenance Records** | Maintenance | Engineering & MX | `work_orders_raw` → `work_orders` | silver `work_orders` (stub-deep) |
| 8 | **Crew Rosters & Duty Logs** | Crew | Crew Resources | `crew_rosters`, `duty_time_logs` (silver) | silver (stub-deep) |
| 9 | **Fuel Uplifts** | Fuel | Fuel Operations | `fuel_uplifts` (silver) | silver (stub-deep) |
| 10 | **Booking Aggregates** | Passenger | Commercial Analytics Ingest | `pnr_aggregates` (silver — aggregates from raw PNR) | silver (stub-deep, PII-shaped) |
| 11 | **Safety Event Log** | Regulatory | Reg Affairs Ingest | `safety_events` (silver) | silver (stub-deep) |

### Aggregate-aligned (3) — unified views composed of source-aligned products

Composed by joining silver outputs of source-aligned products. Internal layers: silver (joined) + gold (rolled up):

| # | Product | Owner | Composed of (input contracts) | Output tables (silver / gold) |
|---|---|---|---|---|
| 12 | **🎯 Global Flight Ops** *(marquee)* | Operations Analytics | Live ADS-B Telemetry + OAG Schedules + Flight Status Events + METAR + Reference Master | silver `global_flight_ops_unified` + gold `global_flight_ops_daily` |
| 13 | **Network Connectivity** | Network Planning | OAG Schedules + Flight Status Events + airports (MCT calc) | silver `viable_connections` |
| 14 | **Flight Emissions** | Sustainability Office | OAG Schedules + Aircraft Registry + Fuel Uplifts | silver `flight_carbon` + gold `emissions_monthly` |

### Consumer-aligned (2) — fit for purpose

Materialized as gold (often a view or thin transform over an aggregate product):

| # | Product | Owner | Composed of | Output tables (gold) |
|---|---|---|---|---|
| 15 | **On-Time Performance** *(Demo 5 Genie target)* | Customer Comms Analytics | Global Flight Ops | gold `otp_metrics_daily` + gold `otp_by_route` |
| 16 | **Reg Compliance Reporting** | Regulatory Affairs | Crew Rosters + Duty Logs + Flight Status Events | gold `part_117_compliance` |

Plus **30+ stub products** (titles + domain + alignment only, no contracts) spread across all eight domains for the marketplace's "hundreds of products" framing.

## What the alignment buys us narratively

**1. The Demo 1 story sharpens.** AI generates a contract for `adsb_v2_raw` — a *source-aligned* bronze table. This is the realistic enterprise pattern: source teams have raw data, no contracts, and need help drafting them. Audiences immediately recognize their own situation.

**2. Demo 2 marketplace can facet on alignment.** Product card shows: `AGGREGATE-ALIGNED · combines 5 source products`. A consumer searching "Global Flight Ops" sees they're getting a *composed* product — and the ontology view shows the composition tree. Slide 17's "ontology beat" lands harder.

**3. Subscription propagation across alignment layers.** Consumer subscribes to `global_flight_ops`. Ontos auto-fans subscription out to all input contracts (`live_flights`, `flight_schedule`, etc.). When DQX rejects a row in `adsb_v2_raw`:
  - Live ADS-B Telemetry owner (Flight Ops Platform) gets notified directly
  - Global Flight Ops owner (Operations Analytics) gets notified — *their input degraded*
  - On-Time Performance owner (Customer Comms Analytics) gets notified — *their input's input degraded*
  - Every subscriber across the three alignment layers gets notified

  This is **the** killer narrative for "trust is engineered, not assumed." It's not just one team alerted — it's the whole dependency chain.

**4. Demo 5 Genie sits on a consumer-aligned product**, not the aggregate. This is the right architectural pattern — business users query OTP via Genie, OTP composes from Global Flight Ops, Global Flight Ops composes from sources. Trust signals chain all the way down.

## Composition diagram (alignment × medallion)

```
ALIGNMENT          MEDALLION LAYER

CONSUMER ────────► gold     On-Time Performance (otp_metrics_daily, otp_by_route)
                            └─ Demo 5 Genie sits here ─┐
                                                       │ derives from
AGGREGATE ───────► gold     Global Flight Ops (global_flight_ops_daily)
                   silver   Global Flight Ops (global_flight_ops_unified)
                            └─ Demo 2 marketplace lands here ─┐
                                                              │ composes from each
                                                              │ source-aligned silver
SOURCE-ALIGNED ──► silver   Live ADS-B (adsb_v2)  ←──── Demo 6 LH Monitor watches here
                            OAG Schedules (oag_schedule)
                            Flight Status (flight_status)
                            METAR (metar_weather)
                            Reference Master (airports/airlines/aircraft_registry)
                              ▲
                              │ DQX promotes by enforcing contract  ←── Demo 3 DQX here
                              │
                   bronze   Live ADS-B (adsb_v2_raw)  ←─── Demo 1 AI gens contract HERE
                            OAG Schedules (oag_schedule_raw)  ← Demo 1 second table
                            Flight Status (flight_status_raw)
                            METAR (metar_raw)
                            (Reference Master skips bronze — vendor-curated)
```

**The narrative arc through this picture, from bottom to top:**

1. **Demo 1**: AI generates the contract for `adsb_v2_raw` (bronze). The domain team had raw data, no contract — AI bootstraps it.
2. **Demo 3**: DQX takes that contract and applies it bronze → silver. Bad rows quarantined. The silver `adsb_v2` is now the contract-backed output of the **Live ADS-B Telemetry** product.
3. **Demo 6**: LH Monitor watches the silver `adsb_v2` for statistical drift.
4. **Demo 2**: Consumer searches "Global Flight Ops" → finds the aggregate product → sees it's composed of 5 source-aligned silvers → subscribes.
5. **Demo 4**: When DQX quarantines a row in Demo 3, the notification fan-out runs UP the composition chain — Live ADS-B owner first, Global Flight Ops owner next, all subscribers at every layer.
6. **Demo 5**: Genie queries the consumer-aligned **On-Time Performance** gold tables. Trust signals chain all the way down through the alignment + layer dependency graph.

The talk's *Four Moves* (Standardize, Generate, Enforce, Discover) map to the picture cleanly — Standardize is ODCS as the format, Generate is Demo 1, Enforce is Demo 3, Discover is Demo 2.

## Contracts in detail — the load-bearing four

The marquee product **Global Flight Ops** has three contracts. Below is the schema/quality/SLA shape for each — these are the ones the demos record against.

### Contract 1: `live_flights` (the Demo 1 + 3 hero)

**Backing table:** `safe_skies.flight_ops.adsb_v2` (gold) sourced from `adsb_v2_raw` (bronze) via DQX.

**Schema (key fields):**
- `icao24` (string, NOT NULL) — 6-char hex transponder ID. *Semantic type: ICAO 24-bit address.*
- `callsign` (string) — flight callsign, e.g. `UAL245`. *Semantic type: ICAO airline + flight number.*
- `lat` (double, NOT NULL, [-90,90])
- `lon` (double, NOT NULL, [-180,180])
- `alt_baro_ft` (int, ≥ 0, ≤ 60000) — barometric altitude. **Quarantine rule: negative altitudes rejected** (Demo 3).
- `alt_geo_ft` (int, ≥ -1000, ≤ 60000) — geometric altitude
- `gs_kt` (double, ≥ 0, ≤ 700) — ground speed
- `vert_rate_fpm` (int)
- `hdg_deg` (double, [0,360))
- `squawk` (string, 4-digit octal)
- `on_ground` (boolean)
- `position_source` (string, enum: ADSB / MLAT / Mode-S)
- `ts_utc` (timestamp, NOT NULL, UTC)
- `dep_iata` (string, 3-char) — joins to `airports`
- `arr_iata` (string, 3-char)

**Quality expectations (ODCS `quality:`):**
- `icao24` matches `^[0-9A-F]{6}$`
- `lat` in [-90,90]; `lon` in [-180,180]
- `alt_baro_ft` ≥ 0 (Demo 3 quarantine rule)
- `ts_utc` ≤ now (no future timestamps)
- Freshness: 95th percentile age of latest row < 30 seconds (Demo 6 LH Monitor drift target)

**SLA:** 99.5% freshness; latency target 30s; retention 90 days hot, 7y archive

**Subscribers** (seeded for Demo 2/4): Ops Control Dashboard, Customer Comms, Network Planning

### Contract 2: `flight_schedule` (the Demo 1 second-table)

**Backing table:** `safe_skies.flight_ops.oag_schedule_clean` from `oag_schedule_raw`.

**Schema (key fields):**
- `flight_key` (string, NOT NULL, PK) — `{airline_iata}{flight_no}_{date}`, e.g. `UA245_20260615`
- `airline_iata` (string, 2-char) — *Semantic type: IATA airline code*
- `airline_icao` (string, 3-char) — *Semantic type: ICAO airline code*
- `flight_no` (int)
- `dep_iata` (string, 3-char) — *Semantic type: IATA airport code*
- `arr_iata` (string, 3-char)
- `dep_icao` (string, 4-char) — *Semantic type: ICAO airport code*
- `arr_icao` (string, 4-char)
- `scheduled_dep_utc` (timestamp)
- `scheduled_arr_utc` (timestamp)
- `aircraft_type_iata` (string, 3-char) — e.g. `738`, `77W`
- `tail_number` (string) — e.g. `N12345`
- `service_date` (date)
- `freq_days_of_week` (string, 7-char binary mask) — e.g. `1111100` for Mon-Fri

**Quality:**
- `airline_iata` matches `^[A-Z0-9]{2}$`
- `dep_iata`/`arr_iata` match `^[A-Z]{3}$` (Demo 3 quarantine rule)
- `scheduled_arr_utc > scheduled_dep_utc` (Demo 3 quarantine rule)
- `flight_no` ≥ 1 and ≤ 9999

**SLA:** 99.9% freshness; published 24h before service date; retention 5y

**Subscribers:** Customer Comms (booking confirmations), Crew Resources, Maintenance

### Contract 3: `flight_status_events`

**Backing table:** `safe_skies.flight_ops.flight_status`

**Schema (key fields):**
- `event_id` (UUID, PK)
- `flight_key` (string, FK to `flight_schedule`)
- `event_type` (enum: OUT, OFF, ON, IN, CANCELLED, DIVERTED, DELAYED)
- `event_ts_utc` (timestamp)
- `delay_minutes` (int, nullable)
- `delay_reason_code` (string, ICAO-standard)

**Quality:** event_ts ≤ now+24h; delay_minutes ≥ -60 (early arrivals allowed up to 60 min)

**SLA:** real-time; latency < 90s from event occurrence

### Contract from Demo 1's AI generation

The AI will generate a *new* contract for **a table without one yet**. Best candidate: **`adsb_v2_raw`** (bronze, dirty) — the AI proposes the rules that, after human edit + approval, become the `live_flights` contract above. This narrative naturally chains Demo 1 → Demo 3.

Second table for Demo 1's "AI generalizes" beat: **`oag_schedule_raw`** → same pattern, produces the `flight_schedule` contract.

## Lifecycle states across the demo set

| Contract | State at start of demo | State at end |
|---|---|---|
| `live_flights` (existing v1.0) | ACTIVE | ACTIVE (unchanged) |
| `flight_schedule` (existing v1.0) | ACTIVE | ACTIVE (unchanged) |
| `live_flights_v2` (the one Demo 1 creates) | does not exist | DRAFT → IN_REVIEW → APPROVED |
| All other product contracts | ACTIVE | ACTIVE |

## Personas → which products they see (Phase 3c trim)

| Persona | Sidebar shows | Home page shows |
|---|---|---|
| **Data Consumer** (Demo 2 protagonist — analyst at Customer Comms) | Home · Data Products · Data Contracts · Search · Glossary · Notifications | Marketplace search, subscribed products, recent contract changes |
| **Data Producer** (Flight Ops Platform team lead) | + Schema Importer · Asset Reviews · Assets · Compliance | Owned products, draft contracts, pending reviews |
| **Data Steward** (Reg Affairs) | + Compliance · Audit · Business Glossaries | Compliance score, recent reviews, glossary changes |
| **Admin** (you, in dev) | Everything | All home sections |

For the demos, we'll record from the Consumer and Producer personas only.

## What this gives the demos

- **Demo 1**: AI generates a contract for `adsb_v2_raw`. The schema, semantic types, and quality expectations the AI produces are directly defensible because they exist in this design.
- **Demo 2**: Consumer searches "Global Flight Ops" → product card shows three output ports (live_flights, flight_schedule, flight_status_events) with trust signals. Subscribes to `live_flights`.
- **Demo 3**: DQX applies `live_flights` against `adsb_v2_raw`; bad rows (negative altitudes) routed to quarantine.
- **Demo 4**: Owner (Flight Ops Platform lead) + subscriber (Customer Comms analyst) receive notifications. Linked back to the contract.
- **Demo 5**: Genie space pointed at Global Flight Ops gold tables; queries answer with trust signals from the contract.
- **Demo 6**: LH Monitor on `adsb_v2`; flight-volume drop fires alert; alert links back to `live_flights` and the owning domain.

## Open questions

- Confirm domain names — alternative: collapse `Reference Data` into Flight Ops to stay strictly with slide 6's seven domains?
- Confirm "Global Flight Ops" as the marquee product (slide spec says so — locking it in)
- Confirm that subscription happens at the **contract** level (i.e., subscribe to `live_flights`, not to "Global Flight Ops" as a whole), or at the **product** level
- Any aviation-domain SMEs at Boeing to fact-check field semantics (e.g., is `position_source` an ADSB/MLAT/Mode-S trichotomy or different in your world)?
