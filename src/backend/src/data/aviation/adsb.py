"""Live ADS-B Telemetry — `adsb_v2_raw` (bronze) and `adsb_v2` (silver).

Fields modeled after the OpenSky REST API; per-15-second tracks for flights that are
"currently airborne" during the demo recording hour. Bronze includes seeded defects
for Demo 3 quarantine: negative altitudes, malformed ICAO24, stale positions, etc.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

import polars as pl

from . import DEFAULT_SEED


def _interpolate_great_circle(
    lat1: float, lon1: float, lat2: float, lon2: float, fraction: float
) -> tuple[float, float]:
    """Approximate intermediate point on a great circle. Good enough for synthetic tracks."""
    # Spherical interpolation
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    l1 = math.radians(lon1)
    l2 = math.radians(lon2)

    dp = p2 - p1
    dl = l2 - l1
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    d = 2 * math.asin(math.sqrt(a))
    if d == 0:
        return lat1, lon1

    A = math.sin((1 - fraction) * d) / math.sin(d)
    B = math.sin(fraction * d) / math.sin(d)
    x = A * math.cos(p1) * math.cos(l1) + B * math.cos(p2) * math.cos(l2)
    y = A * math.cos(p1) * math.sin(l1) + B * math.cos(p2) * math.sin(l2)
    z = A * math.sin(p1) + B * math.sin(p2)
    p_int = math.atan2(z, math.sqrt(x * x + y * y))
    l_int = math.atan2(y, x)
    return math.degrees(p_int), math.degrees(l_int)


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    brg = math.degrees(math.atan2(x, y))
    return (brg + 360) % 360


def _altitude_profile_ft(fraction: float, cruise_alt_ft: int) -> int:
    """V-shaped: climb 0..0.15, cruise 0.15..0.85, descent 0.85..1.0."""
    if fraction < 0.15:
        return int(cruise_alt_ft * (fraction / 0.15))
    if fraction < 0.85:
        return cruise_alt_ft
    return int(cruise_alt_ft * (1 - (fraction - 0.85) / 0.15))


def _speed_profile_kt(fraction: float, cruise_kt: int) -> float:
    if fraction < 0.1:
        return cruise_kt * (fraction / 0.1) * 0.7
    if fraction < 0.9:
        return cruise_kt + (random_jitter := 0)  # caller jitters
    return cruise_kt * (1 - (fraction - 0.9) / 0.1) * 0.7


def build_adsb_v2_raw(
    schedule_silver: pl.DataFrame,
    aircraft: pl.DataFrame,
    airports: pl.DataFrame,
    n_active_flights: int = 50,
    pings_per_flight: int = 240,  # 240 × 15s = 1 hour
    seed: int = DEFAULT_SEED,
    n_dirty_rows: int = 150,
    demo_window_center: Optional[datetime] = None,
) -> pl.DataFrame:
    """Generate per-15s ADS-B telemetry for a subset of scheduled flights.

    The "demo recording hour" is centered on `demo_window_center` (defaults to noon UTC
    on the service date). For each active flight, we materialize a great-circle track
    with realistic altitude/speed profiles, then mix in defect seeds.
    """
    rng = random.Random(seed)

    if schedule_silver.height == 0:
        raise ValueError("schedule_silver must be non-empty")

    # Pick flights — exclude rows with the silver guard column if present
    if "_dq_quarantine_seed" in schedule_silver.columns:
        candidate = schedule_silver.filter(~pl.col("_dq_quarantine_seed"))
    else:
        candidate = schedule_silver
    if candidate.height < n_active_flights:
        n_active_flights = candidate.height
    chosen = candidate.sample(n=n_active_flights, seed=seed)

    airport_idx = {row["iata"]: row for row in airports.to_dicts()}
    aircraft_idx = {row["tail_number"]: row for row in aircraft.to_dicts()}

    if demo_window_center is None:
        # Center the recording window at noon UTC on the service date
        any_flight = chosen.row(0, named=True)
        sdate = any_flight["service_date"]
        demo_window_center = datetime(sdate.year, sdate.month, sdate.day, 12, 0, 0, tzinfo=timezone.utc)

    rows = []
    for flight in chosen.to_dicts():
        dep = airport_idx.get(flight["dep_iata"])
        arr = airport_idx.get(flight["arr_iata"])
        ac = aircraft_idx.get(flight["tail_number"])
        if not dep or not arr or not ac:
            continue

        # Cruise altitude depends on aircraft size
        if ac["mtow_kg"] > 200000:
            cruise_alt = rng.choice([35000, 37000, 39000, 41000])
            cruise_kt = rng.randint(460, 490)
        elif ac["mtow_kg"] > 80000:
            cruise_alt = rng.choice([33000, 35000, 37000])
            cruise_kt = rng.randint(430, 470)
        else:
            cruise_alt = rng.choice([28000, 30000, 32000, 34000])
            cruise_kt = rng.randint(380, 440)

        bearing = _bearing_deg(dep["lat"], dep["lon"], arr["lat"], arr["lon"])

        # Stagger each flight's track-start so they're spread within the demo hour
        offset_minutes = rng.uniform(-25, 25)
        track_start = demo_window_center + timedelta(minutes=offset_minutes)

        prev_alt = 0
        for ping_i in range(pings_per_flight):
            fraction = ping_i / pings_per_flight
            lat, lon = _interpolate_great_circle(
                dep["lat"], dep["lon"], arr["lat"], arr["lon"], fraction
            )
            # Add small lateral jitter
            lat += rng.gauss(0, 0.005)
            lon += rng.gauss(0, 0.005)

            alt_baro = _altitude_profile_ft(fraction, cruise_alt) + rng.randint(-50, 50)
            alt_geo = alt_baro + rng.randint(-100, 200)
            gs = _speed_profile_kt(fraction, cruise_kt) + rng.gauss(0, 8)
            gs = max(0.0, gs)
            vert_rate_fpm = (alt_baro - prev_alt) * 4  # 15s ping → /min = ×4
            prev_alt = alt_baro

            on_ground = alt_baro < 100 and (fraction < 0.02 or fraction > 0.98)
            ts = track_start + timedelta(seconds=ping_i * 15)
            position_source = rng.choices(["ADSB", "MLAT", "Mode-S"], weights=[85, 10, 5])[0]

            rows.append({
                "icao24": ac["icao24"],
                "callsign": f"{flight['airline_icao']}{flight['flight_no']}".ljust(8),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "alt_baro_ft": int(alt_baro),
                "alt_geo_ft": int(alt_geo),
                "gs_kt": round(gs, 1),
                "vert_rate_fpm": int(vert_rate_fpm),
                "true_track_deg": round((bearing + rng.gauss(0, 2)) % 360, 1),
                "squawk": "{:04o}".format(rng.randint(1, 0o7777)),
                "on_ground": on_ground,
                "position_source": position_source,
                "ts_utc": ts,
                "last_contact_utc": ts + timedelta(seconds=rng.randint(0, 4)),
                "dep_iata": flight["dep_iata"],
                "arr_iata": flight["arr_iata"],
                "category": rng.choice([5, 6, 7, 8]),  # medium/large jets
                "_dq_quarantine_seed": False,
            })

    df = pl.DataFrame(rows)
    df = _seed_adsb_defects(df, n_dirty_rows, rng)
    return df


def _seed_adsb_defects(df: pl.DataFrame, n_dirty: int, rng: random.Random) -> pl.DataFrame:
    """Mix in defects matching dais-aviation-data-research.md §6 ADS-B catalog."""
    if n_dirty <= 0 or df.height == 0:
        return df

    indices = rng.sample(range(df.height), min(n_dirty, df.height))
    rows = df.to_dicts()
    for j, idx in enumerate(indices):
        defect = j % 5
        if defect == 0:
            rows[idx]["alt_baro_ft"] = -rng.randint(100, 5000)  # negative altitude
        elif defect == 1:
            rows[idx]["icao24"] = rng.choice(["ZZZZZZ", "gg1234", "AB12", ""])  # malformed
        elif defect == 2:
            rows[idx]["lat"] = 91.0  # out of WGS-84 range
        elif defect == 3:
            rows[idx]["vert_rate_fpm"] = rng.randint(50000, 100000)  # impossible
        else:
            # Stale: last_contact 120s after ts_utc
            rows[idx]["last_contact_utc"] = rows[idx]["ts_utc"] + timedelta(seconds=180)
        rows[idx]["_dq_quarantine_seed"] = True

    return pl.DataFrame(rows)


def build_adsb_v2_silver(bronze: pl.DataFrame) -> pl.DataFrame:
    """Clean silver = bronze minus defect-seeded rows."""
    return bronze.filter(~pl.col("_dq_quarantine_seed")).drop("_dq_quarantine_seed")
