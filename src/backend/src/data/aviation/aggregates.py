"""Aggregate-aligned (`global_flight_ops_*`) and consumer-aligned (`otp_*`) products.

These compose source-aligned silvers into joined/aggregated views, modeling the
real data-mesh pattern where Operations Analytics owns the cross-source product
and Customer Comms Analytics owns the consumer-facing OTP product.
"""
from __future__ import annotations

import polars as pl


def build_global_flight_ops_unified(
    schedule_silver: pl.DataFrame,
    status_silver: pl.DataFrame,
    aircraft: pl.DataFrame,
    airports: pl.DataFrame,
) -> pl.DataFrame:
    """Per-flight unified silver view: schedule + last-known status + aircraft + airport refs."""

    # Aggregate status per flight: latest event_type + total delay
    status_per_flight = (
        status_silver.sort("event_ts_utc")
        .group_by("flight_key")
        .agg([
            pl.col("event_type").last().alias("last_event_type"),
            pl.col("delay_minutes").max().alias("max_delay_minutes"),
            pl.col("event_ts_utc").max().alias("last_event_ts_utc"),
        ])
    )

    aircraft_lookup = aircraft.select(["tail_number", "mtow_kg", "manufacturer", "model"])
    dep_lookup = airports.select(pl.col("iata").alias("dep_iata"), pl.col("name").alias("dep_name"), pl.col("city").alias("dep_city"), pl.col("country_iso").alias("dep_country"))
    arr_lookup = airports.select(pl.col("iata").alias("arr_iata"), pl.col("name").alias("arr_name"), pl.col("city").alias("arr_city"), pl.col("country_iso").alias("arr_country"))

    sched_cols = [c for c in schedule_silver.columns if c != "_dq_quarantine_seed"]

    return (
        schedule_silver.select(sched_cols)
        .join(status_per_flight, on="flight_key", how="left")
        .join(aircraft_lookup, on="tail_number", how="left")
        .join(dep_lookup, on="dep_iata", how="left")
        .join(arr_lookup, on="arr_iata", how="left")
    )


def build_global_flight_ops_daily(unified: pl.DataFrame) -> pl.DataFrame:
    """Per-day rollup by airline and route."""
    return (
        unified.group_by(["service_date", "airline_iata", "dep_iata", "arr_iata"])
        .agg([
            pl.col("flight_key").n_unique().alias("flight_count"),
            pl.col("seat_capacity").sum().alias("total_seats"),
            pl.col("max_delay_minutes").mean().alias("avg_delay_minutes"),
            (pl.col("last_event_type") == "CANCELLED").sum().alias("cancellations"),
            (pl.col("last_event_type") == "DIVERTED").sum().alias("diversions"),
        ])
    )


def build_otp_metrics_daily(unified: pl.DataFrame) -> pl.DataFrame:
    """Consumer-aligned On-Time Performance per airline per day.

    Industry standards: D0 = on-time (0 min late), D15 = within 15 min of schedule, D60 = within 60.
    """
    return (
        unified.group_by(["service_date", "airline_iata"])
        .agg([
            pl.col("flight_key").n_unique().alias("flights"),
            (pl.col("max_delay_minutes").fill_null(0) <= 0).sum().alias("d0_count"),
            (pl.col("max_delay_minutes").fill_null(0) <= 15).sum().alias("d15_count"),
            (pl.col("max_delay_minutes").fill_null(0) <= 60).sum().alias("d60_count"),
            (pl.col("last_event_type") == "CANCELLED").sum().alias("cancellations"),
        ])
        .with_columns([
            (pl.col("d0_count") * 100.0 / pl.col("flights")).round(2).alias("d0_pct"),
            (pl.col("d15_count") * 100.0 / pl.col("flights")).round(2).alias("d15_pct"),
            (pl.col("d60_count") * 100.0 / pl.col("flights")).round(2).alias("d60_pct"),
        ])
    )


def build_otp_by_route(unified: pl.DataFrame) -> pl.DataFrame:
    """OTP rolled by origin–destination route."""
    return (
        unified.group_by(["service_date", "dep_iata", "arr_iata"])
        .agg([
            pl.col("flight_key").n_unique().alias("flights"),
            pl.col("max_delay_minutes").mean().alias("avg_delay_minutes"),
            (pl.col("max_delay_minutes").fill_null(0) <= 15).sum().alias("d15_count"),
        ])
        .with_columns(
            (pl.col("d15_count") * 100.0 / pl.col("flights")).round(2).alias("d15_pct"),
        )
    )


def build_flight_carbon(
    schedule_silver: pl.DataFrame,
    aircraft: pl.DataFrame,
) -> pl.DataFrame:
    """Per-flight estimated CO2 + fuel burn, Cirium-shape."""
    # Heuristic: fuel burn = MTOW * block hours * factor; CO2 = fuel kg * 3.16 (jet A1 conversion)
    aircraft_lookup = aircraft.select(["tail_number", "mtow_kg"])
    return (
        schedule_silver.select([c for c in schedule_silver.columns if c != "_dq_quarantine_seed"])
        .join(aircraft_lookup, on="tail_number", how="left")
        .with_columns([
            (pl.col("scheduled_arr_utc") - pl.col("scheduled_dep_utc")).dt.total_seconds().alias("block_seconds"),
        ])
        .with_columns([
            (pl.col("block_seconds") / 3600.0).alias("block_hours"),
        ])
        .with_columns([
            (pl.col("mtow_kg") * pl.col("block_hours") * 0.04).round(0).alias("est_fuel_kg"),
        ])
        .with_columns([
            (pl.col("est_fuel_kg") * 3.16).round(0).alias("est_co2_kg"),
        ])
        .with_columns([
            (pl.col("est_co2_kg") / pl.col("seat_capacity")).round(2).alias("est_co2_kg_per_seat"),
        ])
        .select([
            "flight_key", "airline_iata", "service_date", "dep_iata", "arr_iata",
            "tail_number", "block_hours", "est_fuel_kg", "est_co2_kg", "est_co2_kg_per_seat",
        ])
    )


def build_part_117_compliance(duty_logs: pl.DataFrame) -> pl.DataFrame:
    """Consumer-aligned Reg Compliance Reporting — daily Part 117 summary."""
    return (
        duty_logs.group_by("log_date")
        .agg([
            pl.col("log_id").count().alias("logs_count"),
            pl.col("exceeded").sum().alias("exceedances"),
            pl.col("flight_duty_period_hours").max().alias("max_fdp_observed"),
            pl.col("flight_duty_period_hours").mean().round(2).alias("avg_fdp"),
        ])
    )
