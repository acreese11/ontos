"""Domain · Team · Data Product · ODCS Contract definitions for the Safe Skies demo.

Authoritative source-of-truth: `plans/dais-domain-model.md`.
Field schemas + quality rules: `plans/dais-aviation-data-research.md`.

Everything here is just data (dicts/lists). The seeder (`seed.py`) consumes these
and calls Ontos manager methods to materialize them.
"""
from __future__ import annotations

from typing import Any

# ──────────────────────────────────────────────────────────────
# Domains — 8 top-level (slide 6's seven plus Reference Data) +
# 9 sub-domains under three of them. Total: 17 domains in a 2-tier hierarchy.
# Products bind to the most specific domain (sub-domain when available; parent otherwise).
# ──────────────────────────────────────────────────────────────
DOMAINS: list[dict[str, Any]] = [
    # ── Top-level (8) ──
    {
        "name": "Flight Ops",
        "description": "Real-time and historical flight operations — what's airborne, what landed, what's late. Owns ADS-B telemetry, status events, weather, and aggregate Flight Ops products.",
    },
    {
        "name": "Scheduling",
        "description": "Forward-looking schedule design, network changes, ATC flow management.",
    },
    {
        "name": "Maintenance",
        "description": "Aircraft fitness, work orders, MEL/CDL deferrals, line maintenance.",
    },
    {
        "name": "Crew",
        "description": "Crew rosters, qualifications, FAA Part 117 duty time tracking.",
    },
    {
        "name": "Regulatory",
        "description": "FAA/EASA/ICAO compliance reporting, safety event logs (ASRS), audit artifacts.",
    },
    {
        "name": "Fuel",
        "description": "Fuel ops, hedging, settlement, sustainable aviation fuel (SAF) mix tracking.",
    },
    {
        "name": "Passenger",
        "description": "Bookings, loyalty, customer flows (PII-aware aggregates only).",
    },
    {
        "name": "Reference Data",
        "description": "Foundational master/lookup data — airports, airlines, aircraft registry. Used by every other domain.",
    },
    # ── Sub-domains under Flight Ops (4) ──
    {
        "name": "Live Telemetry",
        "parent": "Flight Ops",
        "description": "Sub-domain for per-second ADS-B / Aireon telemetry. Highest-volume data in the org.",
    },
    {
        "name": "Flight Status",
        "parent": "Flight Ops",
        "description": "Sub-domain for OOOI events, delays, cancellations, diversions. Real-time within ~6 seconds.",
    },
    {
        "name": "Aviation Weather",
        "parent": "Flight Ops",
        "description": "Sub-domain for METAR, TAF, SIGMET, and other weather feeds consumed by dispatch and ops control.",
    },
    {
        "name": "Operational Aggregates",
        "parent": "Flight Ops",
        "description": "Sub-domain for aggregate-aligned products: Global Flight Ops, Flight Emissions, etc.",
    },
    # ── Sub-domains under Scheduling (2) ──
    {
        "name": "OAG Ingest",
        "parent": "Scheduling",
        "description": "Sub-domain for ingesting and curating commercial schedule data from OAG.",
    },
    {
        "name": "ATC Flow",
        "parent": "Scheduling",
        "description": "Sub-domain for ATC Traffic Management Initiatives, NOTAMs, and airspace events.",
    },
    # ── Sub-domains under Reference Data (3) ──
    {
        "name": "Geography",
        "parent": "Reference Data",
        "description": "Sub-domain for airports, runways, geographic master data.",
    },
    {
        "name": "Industry",
        "parent": "Reference Data",
        "description": "Sub-domain for airline master, aviation industry codes, alliance memberships.",
    },
    {
        "name": "Fleet",
        "parent": "Reference Data",
        "description": "Sub-domain for aircraft registry, type catalog, MTOW, cabin configuration data.",
    },
]

# ──────────────────────────────────────────────────────────────
# Teams (one or two per domain)
# ──────────────────────────────────────────────────────────────
TEAMS: list[dict[str, Any]] = [
    # Flight Ops
    {"name": "flight-ops-platform", "title": "Flight Ops Platform", "description": "Owns ADS-B ingest + flight status events.", "domain": "Flight Ops"},
    {"name": "operations-analytics", "title": "Operations Analytics", "description": "Owns the aggregate Global Flight Ops product.", "domain": "Flight Ops"},
    {"name": "operations-ingest", "title": "Operations Ingest", "description": "Owns METAR + weather feeds.", "domain": "Flight Ops"},
    {"name": "sustainability-office", "title": "Sustainability Office", "description": "Owns Flight Emissions product.", "domain": "Flight Ops"},
    # Scheduling
    {"name": "schedule-data-ops", "title": "Schedule Data Ops", "description": "Owns OAG ingest + schedule curation.", "domain": "Scheduling"},
    {"name": "network-planning", "title": "Network Planning", "description": "Owns ATC Flow + Network Connectivity.", "domain": "Scheduling"},
    # Maintenance
    {"name": "engineering-mx", "title": "Engineering & Maintenance", "description": "Owns work orders + aircraft fitness state.", "domain": "Maintenance"},
    # Crew
    {"name": "crew-resources", "title": "Crew Resources", "description": "Owns crew rosters + duty time logs.", "domain": "Crew"},
    # Regulatory
    {"name": "reg-affairs", "title": "Regulatory Affairs", "description": "Owns compliance reporting + safety event log.", "domain": "Regulatory"},
    # Fuel
    {"name": "fuel-operations", "title": "Fuel Operations", "description": "Owns fuel uplifts + SAF tracking.", "domain": "Fuel"},
    # Passenger
    {"name": "commercial-analytics", "title": "Commercial Analytics", "description": "Owns booking aggregates + customer flows.", "domain": "Passenger"},
    {"name": "customer-comms-analytics", "title": "Customer Comms Analytics", "description": "Owns On-Time Performance for customer-facing reports.", "domain": "Passenger"},
    # Reference Data
    {"name": "data-platform", "title": "Data Platform", "description": "Owns the aviation reference master data.", "domain": "Reference Data"},
]

# ──────────────────────────────────────────────────────────────
# ODCS v3.1 contract definitions (real, with schema + quality)
# ──────────────────────────────────────────────────────────────
CATALOG = "safe_skies"


def _schema_entry(
    *,
    name: str,
    server_path: str,
    properties: list,
    description: str = None,
    business_name: str = None,
    tags: list[str] = None,
) -> dict:
    """One physical-table schema entry inside a contract's schemas list.

    Use multiple of these inside a single contract when several tables share a
    trust boundary (same release cadence, same SLA, same owning team).
    """
    return {
        "name": name,
        "physicalName": server_path,
        "physicalType": "table",
        "description": description or f"Physical Delta table: {server_path}. Promoted from bronze via DQX-enforced contract.",
        "businessName": business_name or name.replace("_", " ").title(),
        "tags": tags or [],
        "properties": properties,
    }


def _contract(
    *,
    name: str,
    version: str,
    owner_team: str,
    description: str,
    quality: list,
    tags: list[str],
    # Single-schema shorthand (the common case):
    server_path: str = None,
    schema_props: list = None,
    # Multi-schema option: pass a list of _schema_entry() dicts here when the
    # contract spans multiple tables that travel together.
    schemas: list = None,
    domain: str = None,
    business_purpose: str = None,
    usage_notes: str = None,
    limitations: str = None,
    refresh_frequency: str = "real-time",
    sla_freshness_minutes: int = 5,
    sla_latency_seconds: int = 30,
    retention_days: int = 90,
    classification: str = "Internal",
    pii_present: bool = False,
    related_product: str = None,
) -> dict:
    """Build a materially-complete ODCS v3.1 dict for the rich create method.

    Every contract gets: description, schema(s) with physicalName, quality rules,
    servers (with catalog/schema properties), tags, roles, team members,
    support channels, SLA properties, and custom properties.
    """
    # Resolve schema list. Multi-schema takes precedence when provided.
    if schemas is None:
        if server_path is None or schema_props is None:
            raise ValueError(f"Contract '{name}' needs either schemas=[...] or both server_path and schema_props")
        schemas = [_schema_entry(
            name=server_path.split(".")[-1],
            server_path=server_path,
            properties=schema_props,
            business_name=name.replace("_", " ").title(),
            tags=tags,
        )]

    # Derive server connectivity from the first schema (all schemas in a contract
    # are assumed to live in the same catalog.schema).
    first_path = schemas[0]["physicalName"]
    catalog, schema_name, _ = first_path.split(".")
    purpose = business_purpose or description
    return {
        "kind": "DataContract",
        "apiVersion": "v3.1.0",
        "version": version,
        "status": "active",
        "name": name,
        "owner": owner_team,
        "domain": domain,
        "dataProduct": related_product,
        "description": {
            "purpose": purpose,
            "usage": usage_notes or "Internal Safe Skies data product. Consume via certified output port; do not query bronze directly.",
            "limitations": limitations or "Synthetic data for DAIS 2026 demo; not for production decisions.",
        },
        "tags": tags,
        "servers": [
            {
                "server": f"databricks-warehouse-{catalog}",
                "type": "databricks",
                "description": f"Production Databricks workspace serving {catalog}.{schema_name}",
                "environment": "prod",
                "catalog": catalog,
                "schema": schema_name,
            }
        ],
        "schema": schemas,
        "qualityRules": quality,
        "roles": [
            {
                "role": "data-steward",
                "description": f"Data steward from {owner_team}; approves contract changes and quality exceptions.",
                "access": "approve",
                "firstLevelApprovers": owner_team,
                "secondLevelApprovers": "data-governance",
            },
            {
                "role": "domain-owner",
                "description": f"Owning domain lead ({domain})",
                "access": "approve",
            },
            {
                "role": "consumer",
                "description": "Read-only access for any subscribed data consumer.",
                "access": "read",
            },
        ],
        "team": [
            {
                "name": f"{owner_team}-lead",
                "username": f"{owner_team}-lead@safe-skies.demo",
                "role": "owner",
                "description": f"Primary owner of {name}",
                "dateIn": "2025-01-01",
            },
            {
                "name": f"{owner_team}-steward",
                "username": f"{owner_team}-steward@safe-skies.demo",
                "role": "data-steward",
                "description": f"Data steward for {name}",
                "dateIn": "2025-01-01",
            },
        ],
        "support": [
            {"channel": "slack", "url": f"https://safe-skies.slack.com/channels/{owner_team}", "description": "Primary support channel"},
            {"channel": "email", "url": f"mailto:{owner_team}@safe-skies.demo", "description": "Async escalation"},
            {"channel": "docs", "url": f"https://docs.safe-skies.demo/products/{name}", "description": "Product documentation"},
        ],
        "slaProperties": [
            {"property": "freshness", "value": str(sla_freshness_minutes), "unit": "minutes", "element": f"{first_path}.ts_utc"},
            {"property": "latency", "value": str(sla_latency_seconds), "unit": "seconds"},
            {"property": "retention", "value": str(retention_days), "unit": "days"},
            {"property": "frequencyOfChange", "value": refresh_frequency, "unit": "policy"},
            {"property": "availability", "value": "99.5", "unit": "percent"},
        ],
        "customProperties": [
            {"property": "dataClassification", "value": classification, "description": "Information classification level"},
            {"property": "containsPII", "value": str(pii_present).lower(), "description": "True if any column carries personally identifiable information"},
            {"property": "certificationLevel", "value": "CERTIFIED", "description": "Data quality certification level"},
            {"property": "ownerSlack", "value": f"#{owner_team}", "description": "Primary Slack channel for owning team"},
            {"property": "lifecyclePolicy", "value": "support-current-and-prior-major", "description": "Contract version support policy"},
        ],
    }


def _prop(
    name,
    ptype,
    required=False,
    unique=False,
    description="",
    pattern=None,
    enum=None,
    max_=None,
    min_=None,
    semantic=None,
    classification="Internal",
    business_name=None,
    critical=False,
    examples=None,
):
    """Build a richly-described ODCS v3.1 schema property dict.

    Every property carries: name, type, requiredness, uniqueness, description,
    businessName, classification (PII/Internal/Public/Restricted), critical-data
    flag, examples, and any value constraints. Property-level customProperties
    carry the semantic type (e.g. 'ICAO 24-bit address').
    """
    if not business_name:
        business_name = name.replace("_", " ").title()
    p = {
        "name": name,
        "logicalType": ptype,
        "required": required,
        "unique": unique,
        "description": description or f"{business_name} ({ptype}).",
        "businessName": business_name,
        "classification": classification,
        "criticalDataElement": critical,
    }
    if pattern: p["pattern"] = pattern
    if enum: p["valueRange"] = {"isInclusive": True, "values": enum}
    if max_ is not None: p["maximum"] = max_
    if min_ is not None: p["minimum"] = min_
    if examples is not None:
        p["examples"] = examples if isinstance(examples, list) else [examples]
    if semantic:
        p["customProperties"] = [{"property": "semanticType", "value": semantic}]
    return p


# ──────────────────────────────────────────────────────────────
# Quality rule helper (ODCS-shaped, DQX-compatible)
# ──────────────────────────────────────────────────────────────
def _qrule(
    name: str,
    description: str,
    *,
    rule: str,
    severity: str = "error",
    dimension: str = "validity",
    business_impact: str = "operational",
    type_: str = "library",
    engine: str = "databricks-dqx",
    must_be: object = None,
    must_be_gt: object = None,
    must_be_ge: object = None,
    must_be_lt: object = None,
    must_be_le: object = None,
    must_be_between_min: object = None,
    must_be_between_max: object = None,
    method: str = "reactive",
    schedule: str = "every-5m",
    unit: str = "rows",
):
    """Build a richly-described ODCS quality rule dict."""
    q = {
        "name": name,
        "description": description,
        "dimension": dimension,
        "businessImpact": business_impact,
        "severity": severity,
        "type": type_,
        "engine": engine,
        "method": method,
        "schedule": schedule,
        "scheduler": "databricks-jobs",
        "unit": unit,
        "rule": rule,
        "level": "object",
    }
    if must_be is not None: q["mustBe"] = must_be
    if must_be_gt is not None: q["mustBeGt"] = must_be_gt
    if must_be_ge is not None: q["mustBeGe"] = must_be_ge
    if must_be_lt is not None: q["mustBeLt"] = must_be_lt
    if must_be_le is not None: q["mustBeLe"] = must_be_le
    if must_be_between_min is not None: q["mustBeBetweenMin"] = must_be_between_min
    if must_be_between_max is not None: q["mustBeBetweenMax"] = must_be_between_max
    return q


# ───── live_flights (Live ADS-B Telemetry) ─────
LIVE_FLIGHTS_CONTRACT = _contract(
    name="live_flights",
    version="1.0.0",
    owner_team="flight-ops-platform",
    domain="Flight Ops",
    description="Per-15-second ADS-B telemetry for every airborne flight in the global network. Sourced from compliant 1090 MHz transponders and aggregated via OpenSky/Aireon-style feeds.",
    server_path=f"{CATALOG}.flight_ops.adsb_v2",
    schema_props=[
        _prop("icao24", "string", required=True, pattern=r"^[0-9A-F]{6}$", description="ICAO 24-bit unique aircraft transponder address. Globally unique per aircraft, broadcast in every ADS-B message.", semantic="ICAO 24-bit address", classification="Restricted", business_name="ICAO 24-bit Address", critical=True, examples=["A78A68", "4AC9F2", "06A1C5"]),
        _prop("callsign", "string", description="Flight callsign as broadcast (airline ICAO + flight number, left-padded with spaces to 8 chars).", semantic="ICAO airline + flight number", classification="Internal", business_name="Callsign", examples=["UAL245  ", "BAW117  "]),
        _prop("lat", "number", required=True, min_=-90, max_=90, description="WGS-84 latitude in decimal degrees, derived from GNSS in the aircraft.", classification="Restricted", business_name="Latitude", critical=True, examples=[37.6188, -33.9434]),
        _prop("lon", "number", required=True, min_=-180, max_=180, description="WGS-84 longitude in decimal degrees.", classification="Restricted", business_name="Longitude", critical=True, examples=[-122.3754, 151.1786]),
        _prop("alt_baro_ft", "integer", min_=0, max_=60000, description="Barometric pressure altitude in feet (reference 1013.25 hPa). Demo 3 quarantine rule: negative values rejected.", classification="Internal", business_name="Barometric Altitude (ft)", critical=True, examples=[35000, 18250]),
        _prop("alt_geo_ft", "integer", description="GPS geometric altitude in feet. Diff from baro indicates pressure/calibration drift.", classification="Internal", business_name="Geometric Altitude (ft)"),
        _prop("gs_kt", "number", min_=0, max_=700, description="Ground speed in knots.", classification="Internal", business_name="Ground Speed (kt)"),
        _prop("vert_rate_fpm", "integer", description="Vertical rate in feet per minute. Positive = climb.", classification="Internal", business_name="Vertical Rate (fpm)"),
        _prop("true_track_deg", "number", min_=0, max_=360, description="True track heading in degrees from true north.", classification="Internal", business_name="True Track (°)"),
        _prop("squawk", "string", pattern=r"^[0-7]{4}$", description="4-digit octal transponder code. 7700=emergency, 7600=radio fail, 7500=hijack, 1200=VFR.", classification="Restricted", business_name="Squawk Code"),
        _prop("on_ground", "boolean", description="True if aircraft is on the ground (derived from altitude + velocity).", classification="Internal", business_name="On Ground"),
        _prop("position_source", "string", enum=["ADSB", "MLAT", "Mode-S"], description="Signal origin: ADSB (direct), MLAT (multilateration-derived), Mode-S (transponder query).", classification="Internal", business_name="Position Source"),
        _prop("ts_utc", "date", required=True, description="Position timestamp in UTC. Drives Demo 6 LH Monitor freshness check.", classification="Internal", business_name="Position Timestamp (UTC)", critical=True),
        _prop("last_contact_utc", "date", description="Most recent any-update timestamp; gap from ts_utc indicates stale position.", classification="Internal", business_name="Last Contact (UTC)"),
    ],
    quality=[
        _qrule("icao24_format", "icao24 must be a 6-character uppercase hex transponder address", rule="icao24 matches '^[0-9A-F]{6}$'", dimension="validity", business_impact="critical"),
        _qrule("alt_baro_positive", "Barometric altitude cannot be negative (physically impossible)", rule="alt_baro_ft >= 0", dimension="validity", business_impact="critical", must_be_ge=0),
        _qrule("lat_in_range", "Latitude must be within WGS-84 valid range", rule="lat between -90 and 90", dimension="validity", must_be_between_min=-90, must_be_between_max=90),
        _qrule("lon_in_range", "Longitude must be within WGS-84 valid range", rule="lon between -180 and 180", dimension="validity", must_be_between_min=-180, must_be_between_max=180),
        _qrule("vert_rate_plausible", "Vertical rate beyond ±10,000 fpm is implausible for commercial aviation", rule="abs(vert_rate_fpm) <= 10000", dimension="validity", severity="warning", must_be_between_min=-10000, must_be_between_max=10000),
        _qrule("position_freshness", "Stale ADS-B positions older than 60s indicate coverage gap", rule="now() - ts_utc <= interval 60 seconds", dimension="freshness", severity="warning", schedule="every-1m"),
    ],
    tags=["adsb", "telemetry", "operational", "source-aligned"],
)


# ───── flight_schedule (OAG Flight Schedules) ─────
FLIGHT_SCHEDULE_CONTRACT = _contract(
    name="flight_schedule",
    version="1.0.0",
    owner_team="schedule-data-ops",
    domain="Scheduling",
    description="Per-flight published schedules. OAG-shape, updated every 15 minutes from supplier feeds.",
    server_path=f"{CATALOG}.scheduling.oag_schedule",
    schema_props=[
        _prop("flight_key", "string", required=True, unique=True, description="{airline_iata}{flight_no}_{YYYYMMDD}"),
        _prop("airline_iata", "string", required=True, pattern=r"^[A-Z0-9]{2}$", semantic="IATA airline code"),
        _prop("airline_icao", "string", pattern=r"^[A-Z]{3}$", semantic="ICAO airline code"),
        _prop("flight_no", "integer", min_=1, max_=9999),
        _prop("dep_iata", "string", required=True, pattern=r"^[A-Z]{3}$", semantic="IATA airport code"),
        _prop("arr_iata", "string", required=True, pattern=r"^[A-Z]{3}$", semantic="IATA airport code"),
        _prop("dep_icao", "string", pattern=r"^[A-Z]{4}$", semantic="ICAO airport code"),
        _prop("arr_icao", "string", pattern=r"^[A-Z]{4}$", semantic="ICAO airport code"),
        _prop("scheduled_dep_utc", "date", required=True),
        _prop("scheduled_arr_utc", "date", required=True),
        _prop("aircraft_type_iata", "string"),
        _prop("aircraft_type_icao", "string"),
        _prop("tail_number", "string", semantic="Aircraft registration"),
        _prop("service_date", "date", required=True),
        _prop("seat_capacity", "integer", min_=19, max_=900),
    ],
    quality=[
        _qrule("airline_iata_format", "Airline IATA must be a 2-character alphanumeric code (A-Z, 0-9)", rule="airline_iata matches '^[A-Z0-9]{2}$'", dimension="validity"),
        _qrule("dep_iata_format", "Departure airport IATA must be a 3-letter uppercase code", rule="dep_iata matches '^[A-Z]{3}$'", dimension="validity"),
        _qrule("arr_iata_format", "Arrival airport IATA must be a 3-letter uppercase code", rule="arr_iata matches '^[A-Z]{3}$'", dimension="validity"),
        _qrule("arrival_after_departure", "Scheduled arrival must be after scheduled departure", rule="scheduled_arr_utc > scheduled_dep_utc", dimension="validity", business_impact="critical"),
        _qrule("distinct_endpoints", "Origin and destination airports must differ", rule="dep_iata != arr_iata", dimension="validity", business_impact="critical"),
        _qrule("flight_no_range", "Flight number must be between 1 and 9999", rule="flight_no between 1 and 9999", dimension="validity", must_be_between_min=1, must_be_between_max=9999),
    ],
    tags=["schedules", "operational", "source-aligned", "oag"],
)


# ───── flight_status_events (3 schemas in 1 contract) ─────
# The raw event stream + two derived views, all materialized by the same job
# and versioned together. The two derived views are filter projections of the
# raw table, so they share trust lineage.
FLIGHT_STATUS_CONTRACT = _contract(
    name="flight_status_events",
    version="1.0.0",
    owner_team="flight-ops-platform",
    domain="Flight Ops",
    description="OOOI (Out, Off, On, In) and irregular-operations events per flight. Real-time within ~6 seconds. One contract exposes the raw stream and two specialized projections (delays-only for OTP analytics, cancellations/diversions for regulatory reporting).",
    schemas=[
        _schema_entry(
            name="flight_status",
            server_path=f"{CATALOG}.flight_ops.flight_status",
            business_name="Flight Status Events (raw)",
            description="Raw event stream — every OOOI/IROP event for every flight.",
            tags=["status", "ooooi", "raw"],
            properties=[
                _prop("event_id", "string", required=True, unique=True),
                _prop("flight_key", "string", required=True, description="FK to flight_schedule"),
                _prop("event_type", "string", required=True, enum=["OUT", "OFF", "ON", "IN", "CANCELLED", "DIVERTED", "DELAYED"]),
                _prop("event_ts_utc", "date", required=True),
                _prop("delay_minutes", "integer", min_=-60, max_=720),
                _prop("delay_reason_code", "string"),
                _prop("dep_gate", "string"),
                _prop("arr_gate", "string"),
                _prop("dep_terminal", "string"),
                _prop("diverted_airport_iata", "string", pattern=r"^[A-Z]{3}$"),
                _prop("data_source", "string", enum=["SCHEDULED", "AIRPORT", "AIRLINE", "ASQP", "FS_INFERRED"]),
            ],
        ),
        _schema_entry(
            name="flight_status_delays",
            server_path=f"{CATALOG}.flight_ops.flight_status_delays",
            business_name="Flight Delays (projection)",
            description="Delay-only projection: rows where event_type='DELAYED' with non-null delay_minutes, enriched with delay-category bucket.",
            tags=["status", "delays", "projection"],
            properties=[
                _prop("event_id", "string", required=True, unique=True),
                _prop("flight_key", "string", required=True),
                _prop("event_ts_utc", "date", required=True),
                _prop("delay_minutes", "integer", required=True, min_=0),
                _prop("delay_reason_code", "string", required=True),
                _prop("delay_category", "string", enum=["WEATHER", "ATC", "CARRIER", "SECURITY", "LATE_AIRCRAFT", "OTHER"], description="Derived bucket per BTS categorization"),
            ],
        ),
        _schema_entry(
            name="flight_status_cancellations",
            server_path=f"{CATALOG}.flight_ops.flight_status_cancellations",
            business_name="Cancellations & Diversions (projection)",
            description="Cancellation/diversion-only projection for regulatory reporting and customer-comms.",
            tags=["status", "cancellations", "regulatory", "projection"],
            properties=[
                _prop("event_id", "string", required=True, unique=True),
                _prop("flight_key", "string", required=True),
                _prop("event_ts_utc", "date", required=True),
                _prop("disposition", "string", required=True, enum=["CANCELLED", "DIVERTED"]),
                _prop("reason_code", "string", required=True),
                _prop("diverted_airport_iata", "string", pattern=r"^[A-Z]{3}$", description="Only populated for DIVERTED rows"),
            ],
        ),
    ],
    quality=[
        _qrule("delay_minutes_range", "Departures more than 60 min early are unrealistic", rule="flight_status.delay_minutes >= -60", dimension="validity", must_be_ge=-60),
        _qrule("cancellation_has_reason", "Cancellations should always carry a reason code (per ICAO recommendation)", rule="flight_status.event_type != 'CANCELLED' OR delay_reason_code is not null", dimension="completeness", severity="warning"),
        _qrule("event_ts_not_future", "Event timestamp cannot be more than 24h in the future", rule="event_ts_utc <= now() + interval 24 hours", dimension="validity"),
        _qrule("ooooi_ordering", "OOOI events for a single flight must occur in sequence (OUT < OFF < ON < IN)", rule="rolling-window OOOI sequence check per flight_key in flight_status", dimension="consistency", severity="warning"),
        _qrule("delays_only_positive", "Delays projection must only contain positive delays", rule="flight_status_delays.delay_minutes > 0", dimension="validity", business_impact="critical"),
        _qrule("cancel_disposition_in_scope", "Cancellations projection must only contain CANCELLED/DIVERTED dispositions", rule="flight_status_cancellations.disposition in ('CANCELLED','DIVERTED')", dimension="validity", business_impact="critical"),
        _qrule("diversion_has_airport", "Diversions must specify the diverted-to airport", rule="flight_status_cancellations.disposition != 'DIVERTED' OR diverted_airport_iata is not null", dimension="completeness", business_impact="critical"),
    ],
    tags=["status", "ooooi", "operational", "source-aligned", "multi-schema"],
)


# ───── aviation_weather (2 schemas in 1 contract) ─────
# The raw METAR stream and a current-state projection — same source, same team,
# same SLA, materialized together.
AVIATION_WEATHER_CONTRACT = _contract(
    name="aviation_weather",
    version="1.0.0",
    owner_team="operations-ingest",
    domain="Flight Ops",
    description="Aviation weather data per airport, with two output ports: the raw hourly METAR observation stream and a current-state projection (latest obs per station, enriched with derived FAA flight category VFR/MVFR/IFR/LIFR).",
    schemas=[
        _schema_entry(
            name="metar_observations",
            server_path=f"{CATALOG}.flight_ops.metar_weather",
            business_name="METAR Observations (raw)",
            description="Hourly METAR weather observations per airport, parsed from NOAA/NWS raw feeds.",
            tags=["weather", "metar", "raw"],
            properties=[
                _prop("station_id", "string", required=True, pattern=r"^[A-Z]{4}$", semantic="ICAO airport code"),
                _prop("observation_time_utc", "date", required=True),
                _prop("wind_direction_deg", "integer", min_=0, max_=360),
                _prop("wind_speed_kt", "integer", min_=0, max_=100),
                _prop("wind_gust_kt", "integer"),
                _prop("visibility_m", "integer", min_=0),
                _prop("temperature_c", "integer", min_=-50, max_=60),
                _prop("dew_point_c", "integer"),
                _prop("altimeter_hpa", "integer", min_=900, max_=1100),
            ],
        ),
        _schema_entry(
            name="airport_weather_current",
            server_path=f"{CATALOG}.flight_ops.airport_weather_current",
            business_name="Current Airport Weather (projection)",
            description="One row per station with the latest observation, enriched with derived flight category. Tuned for dispatch/ops-control dashboards.",
            tags=["weather", "current", "projection"],
            properties=[
                _prop("station_id", "string", required=True, unique=True, pattern=r"^[A-Z]{4}$"),
                _prop("observation_time_utc", "date", required=True),
                _prop("wind_direction_deg", "integer", min_=0, max_=360),
                _prop("wind_speed_kt", "integer", min_=0, max_=100),
                _prop("visibility_m", "integer", min_=0),
                _prop("ceiling_ft", "integer", description="Lowest broken/overcast cloud layer in feet AGL"),
                _prop("temperature_c", "integer", min_=-50, max_=60),
                _prop("flight_category", "string", required=True, enum=["VFR", "MVFR", "IFR", "LIFR"], description="Derived per FAA: VFR > 3000ft & >5sm vis, MVFR 1000-3000ft or 3-5sm, IFR 500-1000ft or 1-3sm, LIFR < 500ft or < 1sm"),
            ],
        ),
    ],
    quality=[
        _qrule("dew_point_le_temp", "Dew point can never exceed air temperature (physical impossibility)", rule="metar_observations.dew_point_c <= temperature_c", dimension="validity", business_impact="critical"),
        _qrule("wind_speed_max", "Sustained wind above 100kt is hurricane-strength and exceedingly rare", rule="metar_observations.wind_speed_kt <= 100", dimension="validity", severity="warning", must_be_le=100),
        _qrule("station_id_format", "Station ID must be a 4-character ICAO airport code", rule="station_id matches '^[A-Z]{4}$'", dimension="validity"),
        _qrule("observation_freshness", "METAR observations should not be more than 90 minutes stale during active flight ops", rule="now() - metar_observations.observation_time_utc < interval 90 minutes", dimension="freshness", severity="warning"),
        _qrule("current_one_row_per_station", "Current projection must have exactly one row per station", rule="airport_weather_current.station_id is unique", dimension="uniqueness", business_impact="critical"),
        _qrule("current_freshness_60min", "Current projection must be no more than 60 min stale", rule="now() - airport_weather_current.observation_time_utc < interval 60 minutes", dimension="freshness", severity="warning"),
        _qrule("current_category_derivation", "Flight category must always be derivable from ceiling + visibility", rule="airport_weather_current.flight_category is not null", dimension="completeness"),
    ],
    tags=["weather", "metar", "operational", "source-aligned", "multi-schema"],
)


# ───── aviation_reference (master data — 3 schemas in 1 contract) ─────
# All three reference tables are refreshed by the same monthly job and share
# a single trust boundary. Consolidating them into one contract keeps versioning,
# SLA, and stewardship aligned with how the data actually evolves.
AVIATION_REFERENCE_CONTRACT = _contract(
    name="aviation_reference",
    version="1.0.0",
    owner_team="data-platform",
    domain="Reference Data",
    description="Authoritative master data for airports, airlines, and aircraft — the foundational reference tables joined by every other Safe Skies product. Refreshed monthly from OurAirports, IATA, and FAA registries; versioned and released atomically.",
    schemas=[
        _schema_entry(
            name="airports",
            server_path=f"{CATALOG}.reference.airports",
            business_name="Airports Master",
            description="Authoritative airport master — ICAO/IATA, location, size class. Updated monthly from OurAirports.",
            tags=["reference", "geography"],
            properties=[
                _prop("icao", "string", required=True, unique=True, pattern=r"^[A-Z]{4}$", semantic="ICAO airport code"),
                _prop("iata", "string", required=True, pattern=r"^[A-Z]{3}$", semantic="IATA airport code"),
                _prop("name", "string", required=True),
                _prop("city", "string"),
                _prop("country_iso", "string", required=True, pattern=r"^[A-Z]{2}$", semantic="ISO 3166 alpha-2 country code"),
                _prop("lat", "number", min_=-90, max_=90),
                _prop("lon", "number", min_=-180, max_=180),
                _prop("elevation_ft", "integer"),
                _prop("size_class", "string", enum=["large", "medium", "small"]),
            ],
        ),
        _schema_entry(
            name="airlines",
            server_path=f"{CATALOG}.reference.airlines",
            business_name="Airlines Master",
            description="Major airline carriers with IATA + ICAO codes, country, and alliance membership.",
            tags=["reference", "industry"],
            properties=[
                _prop("iata", "string", required=True, unique=True, pattern=r"^[A-Z0-9]{2}$"),
                _prop("icao", "string", required=True, pattern=r"^[A-Z]{3}$"),
                _prop("name", "string", required=True),
                _prop("country_iso", "string", required=True, pattern=r"^[A-Z]{2}$"),
                _prop("alliance", "string"),
            ],
        ),
        _schema_entry(
            name="aircraft_registry",
            server_path=f"{CATALOG}.reference.aircraft_registry",
            business_name="Aircraft Registry",
            description="Aircraft registry — tail number, ICAO 24-bit address, type, MTOW, cabin config, operator.",
            tags=["reference", "fleet"],
            properties=[
                _prop("tail_number", "string", required=True, unique=True, semantic="Aircraft registration"),
                _prop("icao24", "string", required=True, unique=True, pattern=r"^[0-9A-F]{6}$", semantic="ICAO 24-bit address"),
                _prop("aircraft_type_icao", "string"),
                _prop("aircraft_type_iata", "string"),
                _prop("manufacturer", "string"),
                _prop("model", "string"),
                _prop("year_manufactured", "integer"),
                _prop("mtow_kg", "integer", description="Maximum Takeoff Weight"),
                _prop("active_status", "string", enum=["ACTIVE", "STORED", "SCRAPPED", "LEASED_OUT", "UNKNOWN"]),
            ],
        ),
    ],
    quality=[
        _qrule("airports_icao_unique", "ICAO airport code must be globally unique in the airports table", rule="icao is unique in airports", dimension="uniqueness", business_impact="critical"),
        _qrule("airports_lat_lon_present", "Every airport must have lat/lon for proximity queries", rule="lat is not null and lon is not null in airports", dimension="completeness"),
        _qrule("airlines_iata_unique", "Airline IATA code must be globally unique in the airlines table", rule="iata is unique in airlines", dimension="uniqueness", business_impact="critical"),
        _qrule("aircraft_icao24_format", "ICAO 24-bit address must be 6 hex characters", rule="icao24 matches '^[0-9A-F]{6}$' in aircraft_registry", dimension="validity", business_impact="critical"),
        _qrule("aircraft_tail_number_unique", "Tail number must be globally unique per ICAO Annex 7", rule="tail_number is unique in aircraft_registry", dimension="uniqueness", business_impact="critical"),
        _qrule("scrapped_not_in_schedules", "Aircraft marked SCRAPPED should not appear in active flight schedules (cross-product hygiene check)", rule="aircraft_registry.active_status != 'SCRAPPED' OR tail_number not in safe_skies.scheduling.oag_schedule", dimension="consistency", severity="warning", type_="sql"),
    ],
    refresh_frequency="monthly",
    sla_freshness_minutes=60 * 24 * 7,  # 7 days
    tags=["reference", "master-data", "source-aligned", "multi-schema"],
)


# ───── ATC: tmi_events + notams ─────
TMI_CONTRACT = _contract(
    name="tmi_events",
    version="1.0.0",
    owner_team="network-planning",
    domain="Scheduling",
    description="FAA Traffic Management Initiatives — ground stops, ground delay programs, airspace flow programs, reroutes.",
    server_path=f"{CATALOG}.scheduling.tmi_events",
    schema_props=[
        _prop("tmi_id", "string", required=True, unique=True),
        _prop("kind", "string", required=True, enum=["GROUND_STOP", "GROUND_DELAY_PROGRAM", "AIRSPACE_FLOW", "REROUTE"]),
        _prop("affected_airport_icao", "string", pattern=r"^[A-Z]{4}$"),
        _prop("affected_airport_iata", "string", pattern=r"^[A-Z]{3}$"),
        _prop("reason", "string", enum=["WEATHER", "VOLUME", "EQUIPMENT", "RUNWAY"]),
        _prop("start_ts_utc", "date", required=True),
        _prop("end_ts_utc", "date", required=True),
        _prop("duration_min", "integer", min_=0),
    ],
    quality=[
        _qrule("end_after_start", "TMI end timestamp must be after start", rule="end_ts_utc > start_ts_utc", dimension="validity", business_impact="critical"),
        _qrule("duration_matches_window", "Reported duration_min should match end-start window", rule="duration_min = datediff(minute, start_ts_utc, end_ts_utc)", dimension="consistency", severity="warning"),
    ],
    tags=["atc", "operational", "source-aligned"],
)

NOTAMS_CONTRACT = _contract(
    name="notams",
    version="1.0.0",
    owner_team="network-planning",
    domain="Scheduling",
    description="Notices to Airmen for airport facilities, runways, and airspace restrictions.",
    server_path=f"{CATALOG}.scheduling.notams",
    schema_props=[
        _prop("notam_id", "string", required=True, unique=True),
        _prop("icao", "string", required=True, pattern=r"^[A-Z]{4}$"),
        _prop("category", "string", enum=["RWY", "TWY", "OBST", "NAV", "AIRSPACE", "FUEL", "LIGHTING"]),
        _prop("summary", "string"),
        _prop("valid_from_utc", "date", required=True),
        _prop("valid_to_utc", "date", required=True),
        _prop("is_active", "boolean"),
    ],
    quality=[
        _qrule("notam_id_format", "NOTAM ID must follow ICAO format A####/YYYY", rule="notam_id matches '^[A-Z][0-9]{4}/[0-9]{4}$'", dimension="validity"),
        _qrule("valid_to_after_from", "NOTAM valid-to must be after valid-from", rule="valid_to_utc > valid_from_utc", dimension="validity"),
        _qrule("airport_icao_known", "NOTAM ICAO airport code must exist in airports master", rule="icao in (select icao from safe_skies.reference.airports)", dimension="consistency", severity="warning", type_="sql"),
    ],
    tags=["atc", "notams", "operational", "source-aligned"],
)


# ───── Aggregate-aligned ─────
# Global Flight Ops exposes three output ports, all derived from the same unified
# join + materialization job: a current-state snapshot, a completed-flight history,
# and an event stream. Single contract = single trust unit = atomic version bump.
GLOBAL_FLIGHT_OPS_CONTRACT = _contract(
    name="global_flight_ops",
    version="1.0.0",
    owner_team="operations-analytics",
    domain="Flight Ops",
    description="Unified per-flight view composing Live ADS-B Telemetry, OAG Schedules, Flight Status Events, Aviation Weather, and Aviation Reference. The single source-of-truth for 'how is this flight going?'. Three output ports tune the same trusted aggregate for different consumption shapes.",
    schemas=[
        _schema_entry(
            name="global_flight_ops_unified",
            server_path=f"{CATALOG}.flight_ops.global_flight_ops_unified",
            business_name="Global Flight Ops (current snapshot)",
            description="One row per active/recent flight with the latest known state. The default port for dashboards asking 'what's happening right now'.",
            tags=["flight-ops", "current", "snapshot"],
            properties=[
                _prop("flight_key", "string", required=True, unique=True),
                _prop("airline_iata", "string", required=True),
                _prop("dep_iata", "string", required=True),
                _prop("arr_iata", "string", required=True),
                _prop("scheduled_dep_utc", "date"),
                _prop("scheduled_arr_utc", "date"),
                _prop("last_event_type", "string"),
                _prop("max_delay_minutes", "integer"),
                _prop("tail_number", "string"),
            ],
        ),
        _schema_entry(
            name="global_flight_ops_history",
            server_path=f"{CATALOG}.flight_ops.global_flight_ops_history",
            business_name="Global Flight Ops (history)",
            description="Completed-flight archive: one row per service-date/flight with actuals and final disposition.",
            tags=["flight-ops", "history", "archive"],
            properties=[
                _prop("flight_key", "string", required=True, unique=True),
                _prop("service_date", "date", required=True),
                _prop("airline_iata", "string", required=True),
                _prop("dep_iata", "string", required=True),
                _prop("arr_iata", "string", required=True),
                _prop("actual_dep_utc", "date"),
                _prop("actual_arr_utc", "date"),
                _prop("block_minutes_actual", "integer"),
                _prop("total_delay_minutes", "integer"),
                _prop("final_disposition", "string", enum=["LANDED", "CANCELLED", "DIVERTED"]),
                _prop("tail_number", "string"),
            ],
        ),
        _schema_entry(
            name="global_flight_ops_event_stream",
            server_path=f"{CATALOG}.flight_ops.global_flight_ops_event_stream",
            business_name="Global Flight Ops (event stream)",
            description="Flat event stream enriched with flight context. Tuned for alerting/event-driven consumers.",
            tags=["flight-ops", "events", "stream"],
            properties=[
                _prop("event_id", "string", required=True, unique=True),
                _prop("event_ts_utc", "date", required=True),
                _prop("event_source", "string", required=True, enum=["FLIGHT_STATUS", "ADSB", "WEATHER", "NOTAM"]),
                _prop("event_type", "string", required=True),
                _prop("flight_key", "string"),
                _prop("airline_iata", "string"),
                _prop("dep_iata", "string"),
                _prop("arr_iata", "string"),
                _prop("payload_json", "string", description="Source-specific event payload, JSON-encoded for schema-agnostic fan-out"),
            ],
        ),
    ],
    quality=[
        _qrule("input_freshness", "Aggregate must be no more than 5 min behind its newest input (Live ADS-B)", rule="now() - max(global_flight_ops_unified.last_event_ts_utc) < interval 5 minutes", dimension="freshness", severity="warning", schedule="every-5m"),
        _qrule("current_flight_key_unique", "Current snapshot: one row per flight", rule="global_flight_ops_unified.flight_key is unique", dimension="uniqueness", business_impact="critical"),
        _qrule("history_only_completed", "History port should never contain in-progress flights", rule="global_flight_ops_history.final_disposition is not null", dimension="completeness", business_impact="critical"),
        _qrule("history_disposition_terminal", "Final disposition must be LANDED/CANCELLED/DIVERTED", rule="global_flight_ops_history.final_disposition in ('LANDED','CANCELLED','DIVERTED')", dimension="validity"),
        _qrule("stream_event_ts_present", "Every event-stream row must carry a UTC timestamp", rule="global_flight_ops_event_stream.event_ts_utc is not null", dimension="completeness", business_impact="critical"),
        _qrule("stream_source_known", "Event source must be a registered source", rule="global_flight_ops_event_stream.event_source in ('FLIGHT_STATUS','ADSB','WEATHER','NOTAM')", dimension="validity"),
        _qrule("flight_count_floor", "Daily flight count should not drop below 80% of the trailing-7-day average (catches upstream ingest gaps)", rule="daily_count >= 0.8 * trailing_7d_avg", dimension="completeness", severity="warning", type_="sql"),
        _qrule("composition_coverage", "Every joined flight should have a corresponding row in OAG schedule + Flight Status", rule="global_flight_ops_unified.flight_key in (select flight_key from safe_skies.scheduling.oag_schedule) and flight_key in (select flight_key from safe_skies.flight_ops.flight_status)", dimension="consistency", type_="sql"),
    ],
    tags=["flight-ops", "aggregate-aligned", "marquee", "multi-schema"],
)

FLIGHT_CARBON_CONTRACT = _contract(
    name="flight_carbon",
    version="1.0.0",
    owner_team="sustainability-office",
    domain="Flight Ops",
    description="Per-flight estimated fuel burn and CO₂ emissions. Cirium-style, derived from schedule + aircraft registry + fuel uplifts.",
    server_path=f"{CATALOG}.flight_ops.flight_carbon",
    schema_props=[
        _prop("flight_key", "string", required=True),
        _prop("block_hours", "number"),
        _prop("est_fuel_kg", "number"),
        _prop("est_co2_kg", "number"),
        _prop("est_co2_kg_per_seat", "number"),
    ],
    quality=[
        _qrule("fuel_kg_positive", "Estimated fuel burn cannot be negative", rule="est_fuel_kg >= 0", dimension="validity", must_be_ge=0),
        _qrule("co2_consistency", "CO₂ should be approximately 3.16× fuel burn for Jet A-1 (within 10% tolerance)", rule="abs(est_co2_kg - 3.16 * est_fuel_kg) / est_co2_kg < 0.1", dimension="consistency", severity="warning"),
        _qrule("per_seat_emissions_band", "Per-seat CO₂ for a commercial flight is typically 50-400 kg; flag extremes for review", rule="est_co2_kg_per_seat between 50 and 400", dimension="validity", severity="warning", must_be_between_min=50, must_be_between_max=400),
        _qrule("aircraft_known", "Flight emissions must reference an aircraft in the registry", rule="tail_number in (select tail_number from safe_skies.reference.aircraft_registry)", dimension="consistency", type_="sql"),
    ],
    tags=["esg", "emissions", "aggregate-aligned"],
)


# ───── Consumer-aligned ─────
OTP_METRICS_CONTRACT = _contract(
    name="otp_metrics",
    version="1.0.0",
    owner_team="customer-comms-analytics",
    domain="Passenger",
    description="On-Time Performance metrics tuned for Customer Comms reporting. D0/D15/D60 per airline per day. Consumer-aligned product — built on Global Flight Ops.",
    server_path=f"{CATALOG}.flight_ops.otp_metrics_daily",
    schema_props=[
        _prop("service_date", "date", required=True),
        _prop("airline_iata", "string", required=True),
        _prop("flights", "integer"),
        _prop("d0_pct", "number", description="% flights on time (within 0 min)"),
        _prop("d15_pct", "number", description="% flights within 15 min"),
        _prop("d60_pct", "number", description="% flights within 60 min"),
        _prop("cancellations", "integer"),
    ],
    quality=[
        _qrule("pct_in_0_100", "All percentage metrics must be in [0, 100]", rule="d0_pct between 0 and 100 and d15_pct between 0 and 100 and d60_pct between 0 and 100", dimension="validity", business_impact="critical"),
        _qrule("d0_le_d15_le_d60", "D0 ≤ D15 ≤ D60 (monotonic cumulative on-time-by-window)", rule="d0_pct <= d15_pct and d15_pct <= d60_pct", dimension="consistency", business_impact="critical"),
        _qrule("flights_floor", "Daily flight count per airline must be ≥ 1 (no orphan rows)", rule="flights >= 1", dimension="completeness", must_be_ge=1),
        _qrule("daily_freshness", "OTP daily aggregate published by 06:00 UTC the following day", rule="max(service_date) >= current_date - interval 1 day", dimension="freshness", severity="warning", schedule="daily-06:00-UTC"),
    ],
    tags=["otp", "customer-facing", "consumer-aligned"],
)


# All real contracts collected. AVIATION_REFERENCE_CONTRACT spans 3 schemas
# (airports/airlines/aircraft_registry); AVIATION_WEATHER_CONTRACT spans 2
# (raw + current); FLIGHT_STATUS_CONTRACT spans 3 (raw + delays + cancellations);
# GLOBAL_FLIGHT_OPS_CONTRACT spans 3 (current + history + event_stream).
ALL_CONTRACTS = [
    LIVE_FLIGHTS_CONTRACT, FLIGHT_SCHEDULE_CONTRACT, FLIGHT_STATUS_CONTRACT,
    AVIATION_WEATHER_CONTRACT, AVIATION_REFERENCE_CONTRACT,
    TMI_CONTRACT, NOTAMS_CONTRACT,
    GLOBAL_FLIGHT_OPS_CONTRACT, FLIGHT_CARBON_CONTRACT,
    OTP_METRICS_CONTRACT,
]


# ──────────────────────────────────────────────────────────────
# Data products (16 real + ~30 stubs)
# ──────────────────────────────────────────────────────────────
def _odps_product(*, name: str, domain: str, owner_team: str, description: str, alignment: str, contract_names: list[str] = None, certification: str = "CERTIFIED") -> dict:
    """Minimal ODPS v1.0.0 product dict for the seeder."""
    contract_names = contract_names or []
    return {
        "kind": "DataProduct",
        "apiVersion": "v1.0.0",
        "version": "1.0.0",
        "status": "active",
        "name": name,
        "description": {
            "purpose": description,
            "usage": "Internal Safe Skies data product — see plans/dais-domain-model.md",
            "limitations": "Synthetic data for DAIS 2026 demo.",
        },
        "domain": domain,
        "owner": owner_team,
        "tags": [alignment],
        "customProperties": [
            {"property": "alignment", "value": alignment},
            {"property": "certificationLevel", "value": certification},
        ],
        "_seed_contract_names": contract_names,  # Used by seeder to bind contracts (stripped before insert)
    }


SOURCE_ALIGNED_PRODUCTS = [
    _odps_product(name="Live ADS-B Telemetry", domain="Live Telemetry", owner_team="flight-ops-platform", description="Per-15-second ADS-B telemetry for every airborne flight. The bronze table adsb_v2_raw is the raw landing zone; the silver table adsb_v2 is the contract-backed output port.", alignment="source-aligned", contract_names=["live_flights"]),
    _odps_product(name="OAG Flight Schedules", domain="OAG Ingest", owner_team="schedule-data-ops", description="Published commercial schedules from OAG ingest. Updated every 15 minutes.", alignment="source-aligned", contract_names=["flight_schedule"]),
    _odps_product(name="Flight Status Events", domain="Flight Status", owner_team="flight-ops-platform", description="OOOI events + delays + cancellations + diversions. Real-time within ~6 seconds. Exposes three output ports (raw stream, delays-only, cancellations/diversions) all backed by a single contract — the projections share trust lineage and release cadence with the raw stream.", alignment="source-aligned", contract_names=["flight_status_events"]),
    _odps_product(name="ATC Flow Initiatives", domain="ATC Flow", owner_team="network-planning", description="FAA TMI events + NOTAMs.", alignment="source-aligned", contract_names=["tmi_events", "notams"]),
    _odps_product(name="METAR Observations", domain="Aviation Weather", owner_team="operations-ingest", description="Aviation weather per airport. Two output ports (raw hourly stream + current-state projection per station with derived flight category) backed by a single contract — they share materialization and SLA.", alignment="source-aligned", contract_names=["aviation_weather"]),
    _odps_product(name="Aviation Reference Master", domain="Geography", owner_team="data-platform", description="Authoritative airport, airline, and aircraft master data. Used by every other product. One contract spans all three schemas — refreshed atomically by the monthly registry job.", alignment="source-aligned", contract_names=["aviation_reference"]),
    _odps_product(name="Aircraft Maintenance Records", domain="Maintenance", owner_team="engineering-mx", description="Open and closed work orders by tail number.", alignment="source-aligned"),
    _odps_product(name="Crew Rosters & Duty Logs", domain="Crew", owner_team="crew-resources", description="Crew assignments + FAA Part 117 duty time logs.", alignment="source-aligned"),
    _odps_product(name="Fuel Uplifts", domain="Fuel", owner_team="fuel-operations", description="Per-flight fuel uplift records including SAF mix.", alignment="source-aligned"),
    _odps_product(name="Booking Aggregates", domain="Passenger", owner_team="commercial-analytics", description="Per-flight booking aggregates (PII redacted to hashed surrogates).", alignment="source-aligned"),
    _odps_product(name="Safety Event Log", domain="Regulatory", owner_team="reg-affairs", description="ASRS-shaped safety event reports — birdstrikes, TCAS RAs, runway incursions, etc.", alignment="source-aligned"),
]

AGGREGATE_ALIGNED_PRODUCTS = [
    _odps_product(name="🎯 Global Flight Ops", domain="Operational Aggregates", owner_team="operations-analytics", description="The unified view of every flight — composed from Live ADS-B Telemetry, OAG Schedules, Flight Status Events, Aviation Weather, and Aviation Reference. Three output ports (current snapshot, completed history, event stream) backed by a single contract; the trio is built atomically by one job and versions together.", alignment="aggregate-aligned", contract_names=["global_flight_ops"], certification="CERTIFIED_GOLD"),
    _odps_product(name="Network Connectivity", domain="OAG Ingest", owner_team="network-planning", description="Viable itineraries computed from schedules + status + MCT rules.", alignment="aggregate-aligned"),
    _odps_product(name="Flight Emissions", domain="Operational Aggregates", owner_team="sustainability-office", description="Per-flight estimated CO₂ + fuel burn for ESG reporting.", alignment="aggregate-aligned", contract_names=["flight_carbon"]),
]

CONSUMER_ALIGNED_PRODUCTS = [
    _odps_product(name="On-Time Performance", domain="Passenger", owner_team="customer-comms-analytics", description="OTP metrics for Customer Comms — D0/D15/D60 per airline per day. The Genie space queries this product.", alignment="consumer-aligned", contract_names=["otp_metrics"], certification="CERTIFIED_GOLD"),
    _odps_product(name="Reg Compliance Reporting", domain="Regulatory", owner_team="reg-affairs", description="FAA Part 117 + safety-event compliance summary, tailored for monthly regulator submission.", alignment="consumer-aligned"),
]

REAL_PRODUCTS = SOURCE_ALIGNED_PRODUCTS + AGGREGATE_ALIGNED_PRODUCTS + CONSUMER_ALIGNED_PRODUCTS


# ──────────────────────────────────────────────────────────────
# Stub products (~30) for marketplace density
# ──────────────────────────────────────────────────────────────
STUB_PRODUCTS = [
    # Flight Ops sub-domains
    {"name": "Crew Briefing Pack", "domain": "Flight Status", "owner_team": "flight-ops-platform", "alignment": "consumer-aligned"},
    {"name": "Runway Friction Reports", "domain": "Aviation Weather", "owner_team": "operations-ingest", "alignment": "source-aligned"},
    {"name": "Diversion Decisions", "domain": "Operational Aggregates", "owner_team": "operations-analytics", "alignment": "aggregate-aligned"},
    # Scheduling sub-domains
    {"name": "Slot Allocations", "domain": "ATC Flow", "owner_team": "network-planning", "alignment": "source-aligned"},
    {"name": "Codeshare Mapping", "domain": "OAG Ingest", "owner_team": "schedule-data-ops", "alignment": "source-aligned"},
    {"name": "Seasonal Schedule Drafts", "domain": "OAG Ingest", "owner_team": "schedule-data-ops", "alignment": "source-aligned"},
    # Maintenance
    {"name": "MEL/CDL Deferrals", "domain": "Maintenance", "owner_team": "engineering-mx", "alignment": "source-aligned"},
    {"name": "Heavy Check Schedule", "domain": "Maintenance", "owner_team": "engineering-mx", "alignment": "source-aligned"},
    {"name": "Aircraft Availability", "domain": "Maintenance", "owner_team": "engineering-mx", "alignment": "aggregate-aligned"},
    {"name": "Spare Parts Inventory", "domain": "Maintenance", "owner_team": "engineering-mx", "alignment": "source-aligned"},
    # Crew
    {"name": "Crew Qualifications", "domain": "Crew", "owner_team": "crew-resources", "alignment": "source-aligned"},
    {"name": "Crew Bidding", "domain": "Crew", "owner_team": "crew-resources", "alignment": "source-aligned"},
    {"name": "Sick Call Tracking", "domain": "Crew", "owner_team": "crew-resources", "alignment": "source-aligned"},
    {"name": "Pilot Training Records", "domain": "Crew", "owner_team": "crew-resources", "alignment": "source-aligned"},
    # Regulatory
    {"name": "FAA Audit Artifacts", "domain": "Regulatory", "owner_team": "reg-affairs", "alignment": "consumer-aligned"},
    {"name": "EASA Compliance", "domain": "Regulatory", "owner_team": "reg-affairs", "alignment": "consumer-aligned"},
    {"name": "ASAP Reports", "domain": "Regulatory", "owner_team": "reg-affairs", "alignment": "source-aligned"},
    # Fuel
    {"name": "Fuel Cost Settlements", "domain": "Fuel", "owner_team": "fuel-operations", "alignment": "aggregate-aligned"},
    {"name": "Hedging Positions", "domain": "Fuel", "owner_team": "fuel-operations", "alignment": "source-aligned"},
    {"name": "SAF Supply Forecast", "domain": "Fuel", "owner_team": "fuel-operations", "alignment": "consumer-aligned"},
    {"name": "Tankering Decisions", "domain": "Fuel", "owner_team": "fuel-operations", "alignment": "aggregate-aligned"},
    # Passenger
    {"name": "PNR History", "domain": "Passenger", "owner_team": "commercial-analytics", "alignment": "source-aligned"},
    {"name": "Loyalty Tier Movements", "domain": "Passenger", "owner_team": "commercial-analytics", "alignment": "source-aligned"},
    {"name": "Baggage Mishandling", "domain": "Passenger", "owner_team": "customer-comms-analytics", "alignment": "consumer-aligned"},
    {"name": "Customer Compensation", "domain": "Passenger", "owner_team": "customer-comms-analytics", "alignment": "consumer-aligned"},
    {"name": "Special Needs Bookings", "domain": "Passenger", "owner_team": "commercial-analytics", "alignment": "source-aligned"},
    {"name": "Codeshare Settlements", "domain": "Passenger", "owner_team": "commercial-analytics", "alignment": "aggregate-aligned"},
    # Reference Data sub-domains
    {"name": "Runway Master", "domain": "Geography", "owner_team": "data-platform", "alignment": "source-aligned"},
    {"name": "Cabin Configuration Master", "domain": "Fleet", "owner_team": "data-platform", "alignment": "source-aligned"},
    {"name": "Aircraft Type Master", "domain": "Fleet", "owner_team": "data-platform", "alignment": "source-aligned"},
    {"name": "Country / Currency Master", "domain": "Geography", "owner_team": "data-platform", "alignment": "source-aligned"},
]


# ──────────────────────────────────────────────────────────────
# Entity relationships — aggregate composes sources, consumer derives from aggregate
# ──────────────────────────────────────────────────────────────
COMPOSITIONS: list[dict] = [
    # Aggregate-aligned products are composedOf their source-aligned inputs
    {"parent": "🎯 Global Flight Ops", "kind": "composedOf", "children": [
        "Live ADS-B Telemetry", "OAG Flight Schedules", "Flight Status Events",
        "METAR Observations", "Aviation Reference Master",
    ]},
    {"parent": "Network Connectivity", "kind": "composedOf", "children": [
        "OAG Flight Schedules", "Flight Status Events", "Aviation Reference Master",
    ]},
    {"parent": "Flight Emissions", "kind": "composedOf", "children": [
        "OAG Flight Schedules", "Aviation Reference Master", "Fuel Uplifts",
    ]},
    # Consumer-aligned products are derivedFrom aggregate / source-aligned
    {"parent": "On-Time Performance", "kind": "derivedFrom", "children": ["🎯 Global Flight Ops"]},
    {"parent": "Reg Compliance Reporting", "kind": "derivedFrom", "children": [
        "Crew Rosters & Duty Logs", "Flight Status Events",
    ]},
]


# ──────────────────────────────────────────────────────────────
# Seeded consumer subscriptions (Demo 2 narrative)
# ──────────────────────────────────────────────────────────────
SUBSCRIPTIONS = [
    # Customer Comms Analytics subscribes to Global Flight Ops (Demo 2's main story)
    {"product": "🎯 Global Flight Ops", "subscriber_team": "customer-comms-analytics"},
    # Operations Analytics subscribes to all source-aligned ops products it composes
    {"product": "Live ADS-B Telemetry", "subscriber_team": "operations-analytics"},
    {"product": "OAG Flight Schedules", "subscriber_team": "operations-analytics"},
    {"product": "Flight Status Events", "subscriber_team": "operations-analytics"},
    # Network Planning subscribes to Schedules
    {"product": "OAG Flight Schedules", "subscriber_team": "network-planning"},
]
