"""Stub generators for products that don't drive a demo directly but need to exist
for marketplace density: maintenance work orders, crew rosters, fuel uplifts,
passenger bookings, safety events.

Each is small (~50-500 rows), realistic-shaped, no defect seeds (no demo coverage)."""
from __future__ import annotations

import hashlib
import random
import uuid
from datetime import datetime, timedelta, timezone

import polars as pl

from . import DEFAULT_SEED


def build_work_orders(aircraft: pl.DataFrame, service_date, seed: int = DEFAULT_SEED) -> pl.DataFrame:
    rng = random.Random(seed)
    types = ["A_CHECK", "B_CHECK", "C_CHECK", "LINE_MX", "AOG", "MEL_DEFER", "CDL_DEFER"]
    statuses = ["OPEN", "OPEN", "IN_PROGRESS", "CLOSED", "CLOSED", "CLOSED"]
    aircraft_list = aircraft.to_dicts()
    rows = []
    base = datetime(service_date.year, service_date.month, service_date.day, tzinfo=timezone.utc)
    for _ in range(300):
        ac = rng.choice(aircraft_list)
        rows.append({
            "wo_id": str(uuid.uuid4()),
            "tail_number": ac["tail_number"],
            "wo_type": rng.choice(types),
            "ata_chapter": rng.randint(21, 80),  # ATA chapter codes
            "summary": f"Routine {rng.choice(types).lower()} on {ac['tail_number']}",
            "opened_ts_utc": base - timedelta(days=rng.randint(0, 90), hours=rng.randint(0, 23)),
            "closed_ts_utc": None if rng.random() < 0.4 else base - timedelta(days=rng.randint(0, 90)),
            "labor_hours": round(rng.uniform(0.5, 120.0), 1),
            "status": rng.choice(statuses),
        })
    return pl.DataFrame(rows)


def build_crew_rosters(service_date, seed: int = DEFAULT_SEED) -> pl.DataFrame:
    rng = random.Random(seed)
    positions = ["CA", "FO", "FA"]  # Captain, First Officer, Flight Attendant
    rows = []
    base = datetime(service_date.year, service_date.month, service_date.day, tzinfo=timezone.utc)
    for i in range(800):
        crew_id = f"CR{i:06d}"
        rows.append({
            "crew_id": crew_id,
            "position": rng.choice(positions),
            "base_iata": rng.choice(["ORD", "DFW", "ATL", "LAX", "JFK", "DEN", "PHX", "SEA"]),
            "duty_start_utc": base + timedelta(hours=rng.randint(0, 23)),
            "duty_end_utc": base + timedelta(hours=rng.randint(24, 36)),
            "duty_hours": round(rng.uniform(4.0, 14.0), 2),
            "flight_segments": rng.randint(1, 6),
        })
    return pl.DataFrame(rows)


def build_duty_time_logs(service_date, seed: int = DEFAULT_SEED) -> pl.DataFrame:
    """FAA Part 117 duty time compliance logs."""
    rng = random.Random(seed)
    rows = []
    base = datetime(service_date.year, service_date.month, service_date.day, tzinfo=timezone.utc)
    for i in range(800):
        flight_duty_period = round(rng.uniform(5.0, 16.0), 2)
        rows.append({
            "log_id": str(uuid.uuid4()),
            "crew_id": f"CR{i:06d}",
            "log_date": service_date,
            "flight_duty_period_hours": flight_duty_period,
            "max_fdp_hours": 13.0,
            "exceeded": flight_duty_period > 13.0,
            "rest_period_hours": round(rng.uniform(8.0, 14.0), 2),
        })
    return pl.DataFrame(rows)


def build_fuel_uplifts(schedule_silver: pl.DataFrame, seed: int = DEFAULT_SEED) -> pl.DataFrame:
    rng = random.Random(seed)
    # One uplift per ~80% of flights
    sample = schedule_silver.sample(fraction=0.8, seed=seed)
    rows = []
    for flight in sample.to_dicts():
        rows.append({
            "uplift_id": str(uuid.uuid4()),
            "flight_key": flight["flight_key"],
            "tail_number": flight["tail_number"],
            "uplift_ts_utc": flight["scheduled_dep_utc"] - timedelta(minutes=rng.randint(30, 90)),
            "fuel_kg": round(rng.uniform(5000, 90000), 0),
            "fuel_cost_usd": round(rng.uniform(3500, 65000), 2),
            "supplier": rng.choice(["EXXON", "SHELL", "BP", "CHEVRON", "SASOL"]),
            "sustainability_pct_saf": round(rng.uniform(0, 5), 2),  # Sustainable Aviation Fuel %
        })
    return pl.DataFrame(rows)


def build_pnr_aggregates(schedule_silver: pl.DataFrame, seed: int = DEFAULT_SEED) -> pl.DataFrame:
    """PNR booking aggregates — PII-shaped per flight (hashed for the demo)."""
    rng = random.Random(seed)
    rows = []
    for flight in schedule_silver.to_dicts():
        bookings = rng.randint(40, flight["seat_capacity"])
        revenue = bookings * rng.randint(150, 900)
        # A hashed surrogate to look PII-shaped without being real PII
        hash_sample = hashlib.sha256(f"pnr-{flight['flight_key']}".encode()).hexdigest()
        rows.append({
            "flight_key": flight["flight_key"],
            "bookings_count": bookings,
            "revenue_usd": revenue,
            "load_factor_pct": round(bookings * 100.0 / flight["seat_capacity"], 1),
            "pax_with_loyalty_count": rng.randint(0, bookings),
            "pax_with_pii_hashed_sample": hash_sample,  # PII pattern bait for AI detection
        })
    return pl.DataFrame(rows)


def build_safety_events(service_date, seed: int = DEFAULT_SEED) -> pl.DataFrame:
    rng = random.Random(seed)
    severities = ["MINOR", "MINOR", "MINOR", "MODERATE", "MAJOR", "INCIDENT"]
    kinds = ["BIRDSTRIKE", "TURBULENCE_INJ", "EMERGENCY_DESCENT", "RUNWAY_INCURSION", "GO_AROUND", "TCAS_RA"]
    rows = []
    base = datetime(service_date.year, service_date.month, service_date.day, tzinfo=timezone.utc)
    for _ in range(40):
        rows.append({
            "report_id": str(uuid.uuid4()),
            "report_ts_utc": base - timedelta(days=rng.randint(0, 30), hours=rng.randint(0, 23)),
            "severity": rng.choice(severities),
            "kind": rng.choice(kinds),
            "narrative": "Routine ASRS-shaped narrative; details redacted for synthetic data",
            "regulatory_flag": rng.random() < 0.2,
        })
    return pl.DataFrame(rows)
