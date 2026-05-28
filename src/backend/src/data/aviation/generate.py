"""Orchestrator: generate all aviation tables and materialize them into safe_skies.

Usage (from the repo root via hatch):

    hatch -e dev run python -m src.data.aviation.generate

Outputs:
    safe_skies.reference.{airports, airlines, aircraft_registry}
    safe_skies.flight_ops.{adsb_v2_raw, adsb_v2, flight_status_raw, flight_status,
                          metar_raw, metar_weather, flight_carbon}
    safe_skies.scheduling.{oag_schedule_raw, oag_schedule, tmi_events, notams}
    safe_skies.maintenance.{work_orders}
    safe_skies.crew.{crew_rosters, duty_time_logs}
    safe_skies.regulatory.{part_117_compliance, safety_events}
    safe_skies.fuel.{fuel_uplifts}
    safe_skies.passenger.{pnr_aggregates}
    safe_skies.flight_ops.{global_flight_ops_unified, global_flight_ops_daily,
                           otp_metrics_daily, otp_by_route}
"""
from __future__ import annotations

import os
from typing import List

from databricks.sdk import WorkspaceClient

from . import DEFAULT_SEED, SERVICE_DATE
from .adsb import build_adsb_v2_raw, build_adsb_v2_silver
from .aggregates import (
    build_flight_carbon,
    build_global_flight_ops_daily,
    build_global_flight_ops_unified,
    build_otp_by_route,
    build_otp_metrics_daily,
    build_part_117_compliance,
)
from .aircraft import build_aircraft_registry
from .airlines import build_airlines
from .airports import load_airports
from .events import (
    build_flight_status_raw,
    build_flight_status_silver,
    build_metar_raw,
    build_metar_silver,
    build_notams,
    build_tmi_events,
)
from .schedules import build_oag_schedule_raw, build_oag_schedule_silver
from .stubs import (
    build_crew_rosters,
    build_duty_time_logs,
    build_fuel_uplifts,
    build_pnr_aggregates,
    build_safety_events,
    build_work_orders,
)
from .uc_writer import WriteResult, ensure_seed_dirs, write_table


def generate_all_dataframes(seed: int = DEFAULT_SEED):
    """Build every dataframe in memory. Returns a dict of (schema, table) → DataFrame."""
    print("Building Reference Master…")
    airports = load_airports()
    airlines = build_airlines()
    aircraft = build_aircraft_registry(airlines, n_aircraft=250, seed=seed)
    print(f"  airports {airports.shape}, airlines {airlines.shape}, aircraft {aircraft.shape}")

    print("Building Source-aligned operational data…")
    oag_raw = build_oag_schedule_raw(airports, airlines, aircraft, n_flights=500, seed=seed)
    oag_silver = build_oag_schedule_silver(oag_raw)
    adsb_raw = build_adsb_v2_raw(oag_silver, aircraft, airports, n_active_flights=50, seed=seed)
    adsb_silver = build_adsb_v2_silver(adsb_raw)
    status_raw = build_flight_status_raw(oag_silver, seed=seed)
    status_silver = build_flight_status_silver(status_raw)
    metar_raw = build_metar_raw(airports, SERVICE_DATE, seed=seed)
    metar_silver = build_metar_silver(metar_raw)
    tmi = build_tmi_events(airports, SERVICE_DATE, seed=seed)
    notams = build_notams(airports, SERVICE_DATE, seed=seed)
    print(f"  oag_raw {oag_raw.shape}, oag_silver {oag_silver.shape}")
    print(f"  adsb_raw {adsb_raw.shape}, adsb_silver {adsb_silver.shape}")
    print(f"  status_raw {status_raw.shape}, status_silver {status_silver.shape}")
    print(f"  metar_raw {metar_raw.shape}, metar_silver {metar_silver.shape}")
    print(f"  tmi_events {tmi.shape}, notams {notams.shape}")

    print("Building stub products…")
    work_orders = build_work_orders(aircraft, SERVICE_DATE, seed=seed)
    crew_rosters = build_crew_rosters(SERVICE_DATE, seed=seed)
    duty_logs = build_duty_time_logs(SERVICE_DATE, seed=seed)
    fuel_uplifts = build_fuel_uplifts(oag_silver, seed=seed)
    pnr_agg = build_pnr_aggregates(oag_silver, seed=seed)
    safety_events = build_safety_events(SERVICE_DATE, seed=seed)
    print(f"  work_orders {work_orders.shape}, crew_rosters {crew_rosters.shape}")
    print(f"  duty_logs {duty_logs.shape}, fuel_uplifts {fuel_uplifts.shape}")
    print(f"  pnr_aggregates {pnr_agg.shape}, safety_events {safety_events.shape}")

    print("Building Aggregate + Consumer-aligned products…")
    unified = build_global_flight_ops_unified(oag_silver, status_silver, aircraft, airports)
    daily = build_global_flight_ops_daily(unified)
    otp_daily = build_otp_metrics_daily(unified)
    otp_route = build_otp_by_route(unified)
    flight_carbon = build_flight_carbon(oag_silver, aircraft)
    part_117 = build_part_117_compliance(duty_logs)
    print(f"  unified {unified.shape}, daily {daily.shape}")
    print(f"  otp_daily {otp_daily.shape}, otp_route {otp_route.shape}")
    print(f"  flight_carbon {flight_carbon.shape}, part_117 {part_117.shape}")

    return {
        # Reference Master
        ("reference", "airports"): airports,
        ("reference", "airlines"): airlines,
        ("reference", "aircraft_registry"): aircraft,
        # Source-aligned bronze + silver
        ("scheduling", "oag_schedule_raw"): oag_raw,
        ("scheduling", "oag_schedule"): oag_silver,
        ("flight_ops", "adsb_v2_raw"): adsb_raw,
        ("flight_ops", "adsb_v2"): adsb_silver,
        ("flight_ops", "flight_status_raw"): status_raw,
        ("flight_ops", "flight_status"): status_silver,
        ("flight_ops", "metar_raw"): metar_raw,
        ("flight_ops", "metar_weather"): metar_silver,
        ("scheduling", "tmi_events"): tmi,
        ("scheduling", "notams"): notams,
        # Stubs
        ("maintenance", "work_orders"): work_orders,
        ("crew", "crew_rosters"): crew_rosters,
        ("crew", "duty_time_logs"): duty_logs,
        ("fuel", "fuel_uplifts"): fuel_uplifts,
        ("passenger", "pnr_aggregates"): pnr_agg,
        ("regulatory", "safety_events"): safety_events,
        # Aggregate-aligned
        ("flight_ops", "global_flight_ops_unified"): unified,
        ("flight_ops", "global_flight_ops_daily"): daily,
        ("flight_ops", "flight_carbon"): flight_carbon,
        # Consumer-aligned
        ("flight_ops", "otp_metrics_daily"): otp_daily,
        ("flight_ops", "otp_by_route"): otp_route,
        ("regulatory", "part_117_compliance"): part_117,
    }


def materialize_to_uc(
    dataframes: dict,
    warehouse_id: str | None = None,
    catalog: str = "safe_skies",
    profile: str | None = None,
) -> List[WriteResult]:
    """Upload every dataframe to UC and materialize as a Delta table.

    `profile` defaults to DATABRICKS_CONFIG_PROFILE if not provided. If neither
    is set, the SDK falls through its standard auth chain (DEFAULT profile,
    env vars, etc.).
    """
    warehouse_id = warehouse_id or os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not warehouse_id:
        raise RuntimeError(
            "DATABRICKS_WAREHOUSE_ID is not set and no warehouse_id was passed. "
            "Set DATABRICKS_WAREHOUSE_ID to the target warehouse id."
        )
    profile = profile or os.environ.get("DATABRICKS_CONFIG_PROFILE")
    w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()

    schemas = sorted({s for s, _ in dataframes.keys()})
    print(f"Ensuring volume seed dirs for: {schemas}")
    ensure_seed_dirs(w, schemas)

    results = []
    for (schema, table), df in dataframes.items():
        # Skip any row-level helper columns
        if "_dq_quarantine_seed" in df.columns and table not in ("oag_schedule_raw", "adsb_v2_raw", "flight_status_raw", "metar_raw"):
            df = df.drop("_dq_quarantine_seed")
        print(f"  → {catalog}.{schema}.{table} ({df.height} rows)…")
        r = write_table(w, warehouse_id, df, schema, table, catalog=catalog)
        print(f"     {r.state}{' ' + r.error if r.error else ''}")
        results.append(r)
    return results


def main() -> None:
    dfs = generate_all_dataframes(seed=DEFAULT_SEED)
    results = materialize_to_uc(dfs)
    failed = [r for r in results if r.state == "FAILED"]
    print()
    print(f"Done. {len(results) - len(failed)} succeeded, {len(failed)} failed.")
    for r in failed:
        print(f"  FAILED {r.schema}.{r.table}: {r.error}")


if __name__ == "__main__":
    main()
