"""OAG Flight Schedules — `oag_schedule_raw` (bronze) and `oag_schedule` (silver).

Bronze has intentional defect seeds for Demo 3's DQX quarantine. Silver is the
clean version produced by dropping defective rows.
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

import polars as pl

from . import DEFAULT_SEED, SERVICE_DATE


def _great_circle_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine great-circle distance in km."""
    import math

    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _estimate_block_minutes(distance_km: float) -> int:
    """Rough block-time estimate: 30min taxi/climb/descent + cruise at ~800 km/h."""
    if distance_km < 100:
        return 30
    return int(30 + (distance_km / 800.0) * 60)


def build_oag_schedule_raw(
    airports: pl.DataFrame,
    airlines: pl.DataFrame,
    aircraft: pl.DataFrame,
    n_flights: int = 500,
    service_date: date = SERVICE_DATE,
    seed: int = DEFAULT_SEED,
    n_dirty_rows: int = 25,
) -> pl.DataFrame:
    """Generate the bronze schedule with defect seeds."""
    rng = random.Random(seed)

    # Top-N airports by size_class for higher-traffic pairs
    big_airports = airports.filter(pl.col("size_class") == "large")
    if big_airports.height < 50:
        big_airports = airports.head(50)

    # Only ACTIVE aircraft can be assigned (mostly)
    active_aircraft = aircraft.filter(pl.col("active_status") == "ACTIVE")
    if active_aircraft.height == 0:
        active_aircraft = aircraft

    airport_records = big_airports.to_dicts()
    airline_iatas = airlines["iata"].to_list()
    aircraft_records = active_aircraft.to_dicts()

    rows = []
    for i in range(n_flights):
        dep = rng.choice(airport_records)
        arr = rng.choice(airport_records)
        while arr["iata"] == dep["iata"]:
            arr = rng.choice(airport_records)

        airline_iata = rng.choice(airline_iatas)
        airline_row = airlines.filter(pl.col("iata") == airline_iata).row(0, named=True)
        airline_icao = airline_row["icao"]

        flight_no = rng.randint(1, 9999)
        flight_key = f"{airline_iata}{flight_no}_{service_date.strftime('%Y%m%d')}"

        # Aircraft assignment — prefer aircraft from same airline if available
        same_airline = [a for a in aircraft_records if a["airline_operator_iata"] == airline_iata]
        ac = rng.choice(same_airline) if same_airline else rng.choice(aircraft_records)

        distance_km = _great_circle_distance_km(dep["lat"], dep["lon"], arr["lat"], arr["lon"])
        block_minutes = _estimate_block_minutes(distance_km)

        # Schedule the departure somewhere in the service date
        dep_hour = rng.randint(0, 23)
        dep_minute = rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])
        scheduled_dep = datetime.combine(service_date, time(dep_hour, dep_minute), tzinfo=timezone.utc)
        scheduled_arr = scheduled_dep + timedelta(minutes=block_minutes)

        # Frequency mask — e.g. 1111100 = Mon-Fri only
        freq_mask = "".join(rng.choice("01") for _ in range(7))
        if freq_mask == "0000000":
            freq_mask = "1111111"  # operating-daily fallback

        rows.append({
            "flight_key": flight_key,
            "airline_iata": airline_iata,
            "airline_icao": airline_icao,
            "flight_no": flight_no,
            "dep_iata": dep["iata"],
            "arr_iata": arr["iata"],
            "dep_icao": dep["icao"],
            "arr_icao": arr["icao"],
            "scheduled_dep_utc": scheduled_dep,
            "scheduled_arr_utc": scheduled_arr,
            "aircraft_type_iata": ac["aircraft_type_iata"],
            "aircraft_type_icao": ac["aircraft_type_icao"],
            "tail_number": ac["tail_number"],
            "service_date": service_date,
            "freq_days_of_week": freq_mask,
            "seat_capacity": ac["seat_economy"] + ac["seat_business"] + ac["seat_first"],
            "update_timestamp": datetime.now(timezone.utc),
            "_dq_quarantine_seed": False,
        })

    df = pl.DataFrame(rows)

    # Seed defects per dais-aviation-data-research.md §6
    df = _seed_schedule_defects(df, n_dirty_rows, rng)
    return df


def _seed_schedule_defects(df: pl.DataFrame, n_dirty: int, rng: random.Random) -> pl.DataFrame:
    """Mix in malformed rows that DQX should quarantine."""
    if n_dirty <= 0 or df.height == 0:
        return df

    indices = rng.sample(range(df.height), min(n_dirty, df.height))

    rows = df.to_dicts()
    for j, idx in enumerate(indices):
        defect = j % 4
        if defect == 0:
            # Negative duration: arrival before departure
            rows[idx]["scheduled_arr_utc"] = rows[idx]["scheduled_dep_utc"] - timedelta(minutes=30)
        elif defect == 1:
            # Malformed IATA — lowercase or wrong length
            rows[idx]["dep_iata"] = rows[idx]["dep_iata"].lower()
        elif defect == 2:
            # flight_no out of range
            rows[idx]["flight_no"] = 0
        else:
            # Same dep/arr airport (impossible)
            rows[idx]["arr_iata"] = rows[idx]["dep_iata"]
            rows[idx]["arr_icao"] = rows[idx]["dep_icao"]
        rows[idx]["_dq_quarantine_seed"] = True

    return pl.DataFrame(rows)


def build_oag_schedule_silver(bronze: pl.DataFrame) -> pl.DataFrame:
    """The clean silver schedule = bronze with all defective rows removed."""
    return bronze.filter(~pl.col("_dq_quarantine_seed")).drop("_dq_quarantine_seed")
