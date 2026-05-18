# Safe Skies — Aviation Data Research

**Source-of-truth for synthetic data schemas, quality rules, and contract design.** Compiled from FlightRadar24, OAG, Cirium, OpenSky Network, NOAA, ICAO, FAA, and adjacent public sources. Cite back to this doc when writing field-level data generators or ODCS contracts.

## 1. ADS-B Telemetry — Live ADS-B product (OpenSky / Cirium Aireon shape)

Sources: [OpenSky REST API](https://openskynetwork.github.io/opensky-api/rest.html) · [ICAO 24-bit address](https://skybrary.aero/articles/24-bit-aircraft-address) · [ADS-B Data Quality research](https://www.researchgate.net/publication/328783875_ADS-B_and_Mode_S_Data_for_Aviation_Meteorology_and_Aircraft_Performance_Modelling)

| Field | Type | Range / Format | Notes / Known Defects |
|---|---|---|---|
| `icao24` | string(6) | `^[0-9A-F]{6}$` — `000000`–`FFFFFF` | Unique 24-bit address. Never null. Example: `A78A68` (N647UA) |
| `callsign` | string(≤8) | left-padded with spaces | Can be null or all-spaces if not broadcast |
| `lat` | float | WGS-84, -90..90 | Null if no position update in 15s |
| `lon` | float | WGS-84, -180..180 | Null if stale |
| `baro_altitude_ft` | int | ~-500..50000 ft | **Defect:** Altitude spikes during Mode S transitions; ~8.7% of samples exceed ICAO RVSM ±245ft tolerance. Quarantine frame-to-frame deltas >500ft |
| `geo_altitude_ft` | int | ~-1000..60000 ft | Often null on older transponders. baro−geo discrepancy = pressure/calibration drift |
| `velocity_ms` | float | 0..900 m/s (≈0..1764 kt) | Unreliable during takeoff/landing transitions |
| `true_track_deg` | float | 0..360 | Can flip between contradictory values for loitering aircraft |
| `vertical_rate_ms` | float | typ -50..+50 m/s (≈±9843 fpm) | **Defect:** Oscillates ±5 m/s during level flight |
| `squawk` | string(4) | octal `[0-7]{4}` | Special: `7700` emergency, `7600` radio fail, `7500` hijack, `1200` VFR |
| `position_source` | int | 0=ADS-B, 1=ASTERIX, 2=MLAT, 3=FLARM | MLAT derived, less precise |
| `spi` | bool | True ~0.1% of time | Special Purpose Indicator |
| `on_ground` | bool | derived | **Defect:** Can flip during approaches in mountainous terrain |
| `time_position_utc` | timestamp | unix seconds | Last position update; `last_contact - time_position > 60s` = stale |
| `last_contact_utc` | timestamp | unix seconds | Last any-update; never null |
| `category` | int | 0..20 | 0=no info; 1-2 light; 3-4 small; 5-6 medium; 7 large; 8-9 heavy; 10+ rotorcraft/UAV |

**Update frequency:** ~1 Hz compliant ADS-B; OpenSky API aggregates with 0–30s latency. [FAA caps total latency at 2.0s](https://avsport.org/docs/metar.pdf) for compliant systems but real-world reaches 30+s in poor coverage.

**ODCS quality rules (Demo 3 quarantine triggers):**
- `^[0-9A-F]{6}$` on `icao24`
- `lat ∈ [-90,90]`, `lon ∈ [-180,180]`
- `baro_altitude_ft ≥ 0` (negative altitudes invalid — Demo 3 hero rule)
- `|baro_altitude_ft - geo_altitude_ft| ≤ 1000` (or null one of them)
- `last_contact_utc - time_position_utc < 60s` (stale position rule)
- `|vertical_rate_ms| < 100` (impossible rates)
- Future timestamps: `time_position_utc ≤ now`

## 2. OAG Schedules — OAG Schedules product

Sources: [OAG flight-data-sets](https://www.oag.com/flight-data-sets) · [OAG Schedules API layout](https://knowledge.oag.com/docs/schedules-api-response-layout-descriptions)

| Field | Type | Format | Notes |
|---|---|---|---|
| `flight_key` | string PK | `{airline_iata}{flight_no}_{date}` | E.g. `UA245_20260615` |
| `airline_iata` | string(2) | `^[A-Z0-9]{2}$` | E.g. `UA`, `BA`, `NH` |
| `airline_icao` | string(3) | `^[A-Z]{3}$` | E.g. `UAL`, `BAW`, `ANA` |
| `flight_no` | int | 1..9999 | Some carriers reuse across markets — disambiguate by date |
| `dep_iata` | string(3) | `^[A-Z]{3}$` | E.g. `LAX`. **Gotcha:** Multi-airport metros share codes; ICAO preferred for uniqueness |
| `arr_iata` | string(3) | `^[A-Z]{3}$` | |
| `dep_icao` | string(4) | `^[A-Z]{4}$` | E.g. `KLAX`, `EGLL` |
| `arr_icao` | string(4) | `^[A-Z]{4}$` | |
| `scheduled_dep_utc` | timestamp | ISO 8601 UTC | |
| `scheduled_arr_utc` | timestamp | ISO 8601 UTC | Must be > scheduled_dep_utc |
| `aircraft_type_iata` | string(3) | E.g. `738`, `321`, `77W` | Not strictly standardized; OAG maps to ICAO |
| `aircraft_type_icao` | string(4) | E.g. `B738`, `A321`, `B77W` | Preferred for ML/analytics |
| `tail_number` | string | E.g. `N123UA`, `G-XLEE` | Can be null for future schedules |
| `service_date` | date | | |
| `freq_days_of_week` | string(7) | bin mask `1111100` | Mon-Fri pattern example |
| `seat_capacity` | int | 19..900 | Often null for future schedules; derive from aircraft type + airline history |
| `update_timestamp` | timestamp | | OAG refreshes every 15min via API; flag stale schedules (>7 days before departure, no update) |

**Update frequency:** Every 15 min via API; 6×/day via SSIM; weekly for analytics.

**Quality rules:**
- `dep_iata != arr_iata`
- `scheduled_arr_utc > scheduled_dep_utc`
- `scheduled_arr_utc < scheduled_dep_utc + 24h` (reject impossible durations — longest commercial flight is ~19h)
- Valid IATA + ICAO codes via join to reference master
- `flight_no ∈ [1, 9999]`

## 3. Flight Status — Cirium FlightStats shape

Sources: [Cirium FlightStats Flight Status](https://developer.cirium.com/apis/flightstats-apis/flight-status) · [FAA ASPM OOOI](https://www.aspm.faa.gov/aspmhelp/index/OOOI_Data.html)

| Field | Type | Format | Notes |
|---|---|---|---|
| `flight_id` | UUID | | Cirium unique identifier |
| `flight_key` | string FK | → schedules | |
| `event_type` | enum | `OUT`, `OFF`, `ON`, `IN`, `CANCELLED`, `DIVERTED`, `DELAYED` | OOOI = Out (gate-out), Off (wheels-off), On (wheels-on), In (gate-in) |
| `event_ts_utc` | timestamp | | |
| `delay_minutes` | int | -60..+600 | Range allows up to 60-min early arrival |
| `delay_reason_code` | string | ICAO standard codes | E.g. `WEATHER`, `MECH`, `CREW`, `ATC`, `AIRPORT`, `OTHER`. **Defect:** ~30% null on cancellations, [77% for OPSNET](https://aspmhelp.faa.gov/index/OPSNET_Delays__Detail_Data_Download.html) |
| `dep_gate` | string | E.g. `B42` | Null until 30min before departure; reassigned 1-2× per flight |
| `arr_gate` | string | | Null pre-departure; not authoritative until within 10min of landing |
| `dep_terminal` | string | E.g. `T3`, `1`, `North` | Varies by airport |
| `diverted_airport_iata` | string(3) | If `event_type=DIVERTED` | |
| `data_source` | enum | `SCHEDULED`, `AIRPORT`, `AIRLINE`, `ASQP`, `FS_INFERRED` | Airport/Airline > Inferred for confidence |

**OOOI timing invariants:**
- `gate_out < wheels_off < wheels_on < gate_in`
- typical `wheels_off - gate_out` = 15-30 min (taxi-out)
- typical `gate_in - wheels_on` = 5-30 min (taxi-in)

**Update frequency:** ~every 6 seconds during active flight.

**Quality rules:**
- `event_ts_utc ≤ now + 24h` (no far-future)
- `delay_minutes ≥ -60`
- Enforce OOOI ordering when multiple events present for same flight
- Mark `data_source = FS_INFERRED` with lower confidence
- Status can regress (e.g., LANDED → DELAYED on data correction) — flag but accept

## 4. METAR Observations — Aviation Weather product

Sources: [NOAA NWS METAR](https://www.weather.gov/asos/METAR.html)

METAR is a structured text format with parsed fields:

| Field | Type | Format | Notes |
|---|---|---|---|
| `station_id` | string(4) | `^[A-Z]{4}$` | US prefixed with `K` (e.g., `KJFK`); intl direct ICAO (`LFPG`) |
| `observation_time_utc` | timestamp | Z-suffixed | METAR raw uses `DDHHMMZ` format |
| `wind_direction_deg` | int | 0..360 OR `VRB` | Variable when calm or <3 kt |
| `wind_speed_kt` | int | 0..50 typ | Gusts encoded `18G28KT` (sustained 18, gust 28) |
| `wind_gust_kt` | int | Null if not gusting | |
| `visibility_m` | int | 0..9999+ | 9999 = ≥10km; `P6SM` in US = >6 statute miles |
| `runway_visual_range_m` | int | Null in VFR | `R04/1200D` = RW 04, 1200m, decreasing |
| `present_weather` | string[] | `RA`, `SN`, `TS`, `BR`, `FG`, etc. | `-RA` light rain, `+TSRA` heavy thunderstorm w/ rain |
| `cloud_layers` | json | Up to 4-6 layers | E.g. `[{cov:"BKN",alt_ft:1500},{cov:"OVC",alt_ft:2500}]`. Coverage: SKC/CLR/FEW/SCT/BKN/OVC |
| `temperature_c` | int | -50..+60 typ | |
| `dew_point_c` | int | ≤ temperature | **Quality rule:** dew_point ≤ temperature always |
| `altimeter_hpa` | int | 950..1050 typ | QNH in hPa; US format A3012 = 30.12 inHg |
| `remarks` | string | `AO2`, `SLP`, etc. | Auto-station codes, sea-level pressure, etc. |

**Update frequency:** Hourly (METAR) + SPECI (special) for significant changes.

**Quality rules:**
- `dew_point_c ≤ temperature_c` (always)
- `wind_speed_kt ≤ 100` (sustained 100 kt is hurricane-strength, rare)
- `observation_time_utc ≤ now`
- Station ID matches `^[A-Z]{4}$`

## 5. Aircraft Registry — Reference Master product

Sources: [Cirium Aircraft Fleet Data](https://www.cirium.com/data/aircraft-fleet-values/) · [FAA N-Number registry](https://registry.faa.gov/aircraftinquiry/search/nnumberinquiry) · [ICAO 24-bit registry](https://skybrary.aero/articles/24-bit-aircraft-address)

| Field | Type | Format | Notes |
|---|---|---|---|
| `tail_number` | string PK | `^[A-Z][A-Z0-9-]{1,9}$` | E.g. `N123UA` (US), `G-XLEE` (UK), `VH-OQF` (AUS). US N-numbers: no `I` or `O` |
| `icao24` | string(6) | `^[0-9A-F]{6}$` | 1:1 with tail (rare re-registration inconsistency) |
| `aircraft_type_icao` | string(4) | E.g. `B777`, `A380`, `E195` | |
| `aircraft_type_iata` | string(3) | E.g. `77W`, `388`, `E95` | |
| `manufacturer` | enum | `Boeing`, `Airbus`, `Embraer`, `ATR`, `Bombardier`, `Cessna`, etc. | |
| `model` | string | E.g. `777-300ER`, `A380-800` | |
| `series` | string | E.g. `300ER`, `-800`, `-E2` | |
| `year_manufactured` | int | | |
| `registration_country` | string(2) | ISO 3166 alpha-2 | Derived from tail prefix |
| `airline_operator_iata` | string(2) | | Null for cargo/lessor fleets |
| `mtow_kg` | int | E.g. 777-300ER ≈ 348,814 kg | Max Takeoff Weight |
| `seat_economy` | int | 0..500 | |
| `seat_business` | int | 0..80 | |
| `seat_first` | int | 0..20 | |
| `active_status` | enum | `ACTIVE`, `STORED`, `SCRAPPED`, `LEASED_OUT`, `UNKNOWN` | Deactivation lag 30-90 days |
| `last_update` | timestamp | | Refresh recommended if >180 days |

**Quality rules:**
- `tail_number` matches country-specific format (US: `^N\d{1,5}[A-HJ-NP-Z]{0,2}$`)
- `icao24` is 6 valid hex chars
- `seat_economy + seat_business + seat_first ≤ mtow_kg / 100` (sanity bound)
- Reject if `active_status=SCRAPPED` but still in active schedules (cross-product check)

## 6. Common defect patterns to seed in bronze (Demo 3 quarantine seeds)

For credible Demo 3 visuals, seed these specific defects into `*_raw` bronze tables:

**`adsb_v2_raw`:**
- ~50 rows with `baro_altitude_ft < 0` (impossible negative altitudes)
- ~20 rows with malformed `icao24` (e.g., `ZZZZZZ`, `gg1234`, lowercase)
- ~10 rows with `lat = 91.0` (out of WGS-84 range)
- ~30 rows with `|vertical_rate_ms| > 100` (impossible climb rate)
- ~40 rows with `last_contact - time_position > 120s` (stale)

**`oag_schedule_raw`:**
- ~5 rows with `scheduled_arr_utc < scheduled_dep_utc` (negative duration)
- ~10 rows with malformed `dep_iata` (e.g., `LA`, `LAXX`, lowercase)
- ~3 rows with `scheduled_dep_utc` in the past beyond schedule window
- ~5 rows with `flight_no = 0` or > 9999

**`flight_status_raw`:**
- ~10 rows with `delay_minutes < -60` (unrealistic early)
- ~5 rows with `event_type=CANCELLED` but null `delay_reason_code`
- ~3 OOOI sequences where ordering is violated (e.g., wheels_on before wheels_off)

**`metar_raw`:**
- ~5 rows with `dew_point_c > temperature_c`
- ~3 rows with `wind_speed_kt = 200` (impossible)
- ~2 rows with malformed `station_id` (`xxxx`, `K12J`)

## 7. Demo-relevant insights from research

1. **ADS-B altitude defect resonance.** ~8.7% of altitude samples exceed ICAO RVSM tolerance — this is a known industry pain point. Demo 3's "negative altitude" quarantine rule lands with the audience because they recognize it.

2. **Cancellation reasons are sparsely populated** (~30% null carrier-wide, [~77% OPSNET](https://aspmhelp.faa.gov/index/OPSNET_Delays__Detail_Data_Download.html)). A contract that requires `delay_reason_code` for cancellations is an obvious win.

3. **Gate reassignment chaos.** Real airports see 3–5 gate changes per flight during peak hours. A contract enforcing immutability after T-30min vs. allowing changes earlier is operationally meaningful.

4. **OOOI timing disputes drive crew pay**. Timing discrepancies (automated ±1 min vs. manual ±5 min) escalate to compensation disputes. SLA on timing accuracy = governance win.

5. **Cabin reconfigs happen unannounced**. Seat count mismatches (predicted vs. actual) > 50 indicate fleet ops anomalies. Cross-product compliance check.

6. **`SCRAPPED` aircraft still in schedules** is a real cross-product hygiene issue. Compliance rule scope.

## 8. Sources cited

- OpenSky REST API — https://openskynetwork.github.io/opensky-api/rest.html
- ICAO 24-bit Addresses — https://skybrary.aero/articles/24-bit-aircraft-address
- OAG Flight Data Sets — https://www.oag.com/flight-data-sets
- OAG Schedules API — https://knowledge.oag.com/docs/schedules-api-response-layout-descriptions
- Cirium Aviation Data — https://www.cirium.com/data/aviation-data/
- Cirium Aircraft Fleet — https://www.cirium.com/data/aircraft-fleet-values/
- Cirium FlightStats API — https://developer.cirium.com/apis/flightstats-apis/flight-status
- NOAA/NWS METAR — https://www.weather.gov/asos/METAR.html
- FAA ASPM OOOI — https://www.aspm.faa.gov/aspmhelp/index/OOOI_Data.html
- FAA Aircraft Registry — https://registry.faa.gov/aircraftinquiry/search/nnumberinquiry
- ADS-B Data Quality research — https://www.researchgate.net/publication/328783875
- ADS-B Latency Analysis — https://www.avionix-tech.com/blog/ADS-B-Data-Latency/
