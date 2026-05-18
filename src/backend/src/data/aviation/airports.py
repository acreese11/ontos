"""Aviation Reference Master / `airports` — curated subset of the OurAirports CC-0 dataset.

We pull the public CSV, filter to large+medium passenger airports with both IATA
and ICAO codes, and trim to columns useful for the demo.
"""
from __future__ import annotations

import io
import urllib.request
from typing import Optional

import polars as pl

OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"


def fetch_ourairports_csv(url: str = OURAIRPORTS_URL) -> bytes:
    """Fetch the OurAirports CSV. Network call; cache the result if you call this often."""
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def build_airports(
    csv_bytes: Optional[bytes] = None,
    n_airports: int = 250,
) -> pl.DataFrame:
    """Build the silver `airports` reference table.

    Args:
        csv_bytes: pre-fetched OurAirports CSV bytes (skip the network call). If
            None, fetches from the public URL.
        n_airports: how many airports to keep (we sort by size class then take top N).

    Returns a Polars DataFrame with columns:
        icao, iata, name, city, country_iso, lat, lon, elevation_ft, size_class
    """
    if csv_bytes is None:
        csv_bytes = fetch_ourairports_csv()

    raw = pl.read_csv(io.BytesIO(csv_bytes))

    # OurAirports column names: ident (ICAO-ish), type, name, latitude_deg,
    # longitude_deg, elevation_ft, iso_country, municipality, iata_code, gps_code
    filtered = (
        raw.filter(
            (pl.col("type").is_in(["large_airport", "medium_airport"]))
            & (pl.col("iata_code").is_not_null())
            & (pl.col("iata_code").str.len_chars() == 3)
            & (pl.col("gps_code").is_not_null())
            & (pl.col("gps_code").str.len_chars() == 4)
            & (pl.col("scheduled_service") == "yes")
        )
        .with_columns(
            # Sort key — large first, then medium, then alphabetical by name for stability
            pl.when(pl.col("type") == "large_airport").then(0).otherwise(1).alias("_size_rank"),
        )
        .sort(["_size_rank", "name"])
        .head(n_airports)
    )

    return filtered.select(
        pl.col("gps_code").alias("icao"),
        pl.col("iata_code").alias("iata"),
        pl.col("name"),
        pl.col("municipality").alias("city"),
        pl.col("iso_country").alias("country_iso"),
        pl.col("latitude_deg").alias("lat"),
        pl.col("longitude_deg").alias("lon"),
        pl.col("elevation_ft").cast(pl.Int32),
        pl.when(pl.col("type") == "large_airport")
        .then(pl.lit("large"))
        .otherwise(pl.lit("medium"))
        .alias("size_class"),
    )
