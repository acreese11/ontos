"""Flight Status Events, METAR Weather, ATC Flow (TMI + NOTAMs)."""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import polars as pl

from . import DEFAULT_SEED


# ---------------------------- Flight Status Events ----------------------------
DELAY_REASONS = [
    "WEATHER", "MECH", "CREW", "ATC", "AIRPORT", "FUEL", "OTHER",
    None, None, None,  # 30% null per research
]

DATA_SOURCES = ["AIRPORT", "AIRPORT", "AIRLINE", "AIRLINE", "ASQP", "FS_INFERRED"]


def build_flight_status_raw(
    schedule_silver: pl.DataFrame,
    seed: int = DEFAULT_SEED,
    n_dirty_rows: int = 25,
) -> pl.DataFrame:
    """Per-flight OOOI events + delays for the day. Multiple events per flight allowed."""
    rng = random.Random(seed)
    rows = []
    for flight in schedule_silver.to_dicts():
        sched_dep = flight["scheduled_dep_utc"]
        sched_arr = flight["scheduled_arr_utc"]

        # 75% On-Time + OOOI sequence; 10% Delayed; 8% Cancelled; 5% Diverted; 2% other
        outcome = rng.choices(
            ["ON_TIME", "DELAYED", "CANCELLED", "DIVERTED"],
            weights=[75, 10, 8, 5],
        )[0]

        if outcome == "CANCELLED":
            rows.append({
                "event_id": str(uuid.uuid4()),
                "flight_key": flight["flight_key"],
                "event_type": "CANCELLED",
                "event_ts_utc": sched_dep - timedelta(hours=rng.randint(1, 12)),
                "delay_minutes": None,
                "delay_reason_code": rng.choice(DELAY_REASONS),
                "dep_gate": None,
                "arr_gate": None,
                "dep_terminal": None,
                "diverted_airport_iata": None,
                "data_source": rng.choice(DATA_SOURCES),
                "_dq_quarantine_seed": False,
            })
            continue

        delay_minutes = 0
        if outcome == "DELAYED":
            delay_minutes = rng.randint(15, 240)

        # OUT / OFF / ON / IN sequence
        out_ts = sched_dep + timedelta(minutes=delay_minutes + rng.randint(-2, 5))
        off_ts = out_ts + timedelta(minutes=rng.randint(8, 25))
        on_ts = sched_arr + timedelta(minutes=delay_minutes + rng.randint(-10, 10))
        in_ts = on_ts + timedelta(minutes=rng.randint(4, 15))

        diverted_to = None
        if outcome == "DIVERTED":
            diverted_to = rng.choice([flight["arr_iata"][:2] + "X", "ORD", "DFW", "ATL"])

        gate = f"{rng.choice(['A','B','C','D','E','F'])}{rng.randint(1, 99)}"
        arr_gate = f"{rng.choice(['A','B','C','D','E','F'])}{rng.randint(1, 99)}"
        for evt_type, ts in [("OUT", out_ts), ("OFF", off_ts), ("ON", on_ts), ("IN", in_ts)]:
            rows.append({
                "event_id": str(uuid.uuid4()),
                "flight_key": flight["flight_key"],
                "event_type": evt_type,
                "event_ts_utc": ts,
                "delay_minutes": delay_minutes if evt_type in ("OUT", "OFF") else None,
                "delay_reason_code": rng.choice(DELAY_REASONS) if delay_minutes > 0 else None,
                "dep_gate": gate,
                "arr_gate": arr_gate if evt_type in ("ON", "IN") else None,
                "dep_terminal": str(rng.randint(1, 5)),
                "diverted_airport_iata": diverted_to if evt_type == "ON" and outcome == "DIVERTED" else None,
                "data_source": rng.choice(DATA_SOURCES),
                "_dq_quarantine_seed": False,
            })

    df = pl.DataFrame(rows)
    df = _seed_status_defects(df, n_dirty_rows, rng)
    return df


def _seed_status_defects(df: pl.DataFrame, n_dirty: int, rng: random.Random) -> pl.DataFrame:
    if n_dirty <= 0 or df.height == 0:
        return df
    indices = rng.sample(range(df.height), min(n_dirty, df.height))
    rows = df.to_dicts()
    for j, idx in enumerate(indices):
        defect = j % 3
        if defect == 0:
            rows[idx]["delay_minutes"] = -rng.randint(61, 180)  # unrealistic early
        elif defect == 1:
            rows[idx]["event_type"] = "CANCELLED"
            rows[idx]["delay_reason_code"] = None  # cancelled without reason
        else:
            # Future timestamp
            rows[idx]["event_ts_utc"] = datetime.now(timezone.utc) + timedelta(days=365)
        rows[idx]["_dq_quarantine_seed"] = True
    return pl.DataFrame(rows)


def build_flight_status_silver(bronze: pl.DataFrame) -> pl.DataFrame:
    return bronze.filter(~pl.col("_dq_quarantine_seed")).drop("_dq_quarantine_seed")


# ---------------------------- METAR Weather ----------------------------
WEATHER_PHENOMENA = ["", "", "", "", "RA", "BR", "FG", "TS", "-RA", "+TSRA", "SN", "HZ"]
CLOUD_COVERAGE = ["SKC", "FEW", "SCT", "BKN", "OVC"]


def build_metar_raw(
    airports: pl.DataFrame,
    service_date,
    hours: int = 24,
    seed: int = DEFAULT_SEED,
    top_n_airports: int = 100,
    n_dirty_rows: int = 10,
) -> pl.DataFrame:
    rng = random.Random(seed)
    top = airports.filter(pl.col("size_class") == "large").head(top_n_airports)
    rows = []
    base_ts = datetime(service_date.year, service_date.month, service_date.day, tzinfo=timezone.utc)
    for ap in top.to_dicts():
        for h in range(hours):
            ts = base_ts + timedelta(hours=h)
            temp = rng.randint(-30, 40)
            dewpoint = temp - rng.randint(0, 20)  # always ≤ temp
            wind_dir = rng.choice([rng.randint(0, 360), None])  # VRB possible
            wind_kt = rng.randint(0, 30)
            wind_gust = wind_kt + rng.randint(0, 15) if wind_kt > 10 and rng.random() < 0.3 else None
            phenomenon = rng.choice(WEATHER_PHENOMENA)
            cloud_cov = rng.choice(CLOUD_COVERAGE)
            cloud_alt = rng.randint(500, 12000) if cloud_cov != "SKC" else None

            rows.append({
                "station_id": ap["icao"],
                "observation_time_utc": ts,
                "wind_direction_deg": wind_dir,
                "wind_speed_kt": wind_kt,
                "wind_gust_kt": wind_gust,
                "visibility_m": rng.choice([1500, 4000, 9999, 9999, 9999]),
                "present_weather": phenomenon,
                "cloud_coverage": cloud_cov,
                "cloud_alt_ft": cloud_alt,
                "temperature_c": temp,
                "dew_point_c": dewpoint,
                "altimeter_hpa": rng.randint(990, 1030),
                "raw_metar": f"{ap['icao']} {ts.strftime('%d%H%M')}Z {wind_dir or 'VRB'}{wind_kt:02d}KT {phenomenon or ''} {cloud_cov}{int((cloud_alt or 0)/100):03d} {temp:02d}/{dewpoint:02d} Q{rng.randint(990,1030)}",
                "_dq_quarantine_seed": False,
            })

    df = pl.DataFrame(rows)
    df = _seed_metar_defects(df, n_dirty_rows, rng)
    return df


def _seed_metar_defects(df: pl.DataFrame, n_dirty: int, rng: random.Random) -> pl.DataFrame:
    if n_dirty <= 0 or df.height == 0:
        return df
    indices = rng.sample(range(df.height), min(n_dirty, df.height))
    rows = df.to_dicts()
    for j, idx in enumerate(indices):
        defect = j % 3
        if defect == 0:
            rows[idx]["dew_point_c"] = rows[idx]["temperature_c"] + 10  # dewpoint > temp
        elif defect == 1:
            rows[idx]["wind_speed_kt"] = 200  # impossible sustained wind
        else:
            rows[idx]["station_id"] = "xxxx"  # malformed
        rows[idx]["_dq_quarantine_seed"] = True
    return pl.DataFrame(rows)


def build_metar_silver(bronze: pl.DataFrame) -> pl.DataFrame:
    return bronze.filter(~pl.col("_dq_quarantine_seed")).drop("_dq_quarantine_seed")


# ---------------------------- ATC Flow: TMI events + NOTAMs ----------------------------
def build_tmi_events(
    airports: pl.DataFrame,
    service_date,
    seed: int = DEFAULT_SEED,
    n_events: int = 80,
) -> pl.DataFrame:
    rng = random.Random(seed)
    large = airports.filter(pl.col("size_class") == "large").to_dicts()
    rows = []
    base_ts = datetime(service_date.year, service_date.month, service_date.day, tzinfo=timezone.utc)
    for i in range(n_events):
        ap = rng.choice(large)
        kind = rng.choice(["GROUND_STOP", "GROUND_DELAY_PROGRAM", "AIRSPACE_FLOW", "REROUTE"])
        start = base_ts + timedelta(hours=rng.randint(0, 23), minutes=rng.choice([0, 15, 30, 45]))
        dur = rng.randint(15, 240)
        rows.append({
            "tmi_id": str(uuid.uuid4()),
            "kind": kind,
            "affected_airport_icao": ap["icao"],
            "affected_airport_iata": ap["iata"],
            "reason": rng.choice(["WEATHER", "VOLUME", "EQUIPMENT", "RUNWAY"]),
            "start_ts_utc": start,
            "end_ts_utc": start + timedelta(minutes=dur),
            "duration_min": dur,
        })
    return pl.DataFrame(rows)


def build_notams(
    airports: pl.DataFrame,
    service_date,
    seed: int = DEFAULT_SEED,
    n_notams: int = 200,
) -> pl.DataFrame:
    rng = random.Random(seed)
    aps = airports.to_dicts()
    rows = []
    base_ts = datetime(service_date.year, service_date.month, service_date.day, tzinfo=timezone.utc)
    categories = ["RWY", "TWY", "OBST", "NAV", "AIRSPACE", "FUEL", "LIGHTING"]
    for i in range(n_notams):
        ap = rng.choice(aps)
        cat = rng.choice(categories)
        valid_from = base_ts - timedelta(days=rng.randint(0, 30))
        valid_to = valid_from + timedelta(days=rng.randint(1, 60))
        rows.append({
            "notam_id": f"A{rng.randint(1000, 9999)}/{service_date.year}",
            "icao": ap["icao"],
            "category": cat,
            "summary": f"{cat} maintenance/restriction at {ap['icao']}",
            "valid_from_utc": valid_from,
            "valid_to_utc": valid_to,
            "is_active": valid_from <= base_ts <= valid_to,
        })
    return pl.DataFrame(rows)
