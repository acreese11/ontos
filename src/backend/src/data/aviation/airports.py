"""Aviation Reference Master / `airports` — curated subset of the OurAirports CC-0 dataset.

The DAIS demo loads from a committed Parquet snapshot
(`snapshots/airports.parquet`, ~14KB, 250 rows) — no network call needed.

`fetch_ourairports_csv` / `build_airports` remain available for refreshing the
snapshot. Run `python -m src.data.aviation.airports --refresh` from the backend
dir to regenerate.
"""
from __future__ import annotations

import io
import urllib.request
from pathlib import Path
from typing import Optional

import polars as pl

OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "airports.parquet"


def fetch_ourairports_csv(url: str = OURAIRPORTS_URL) -> bytes:
    """Fetch the OurAirports CSV. Network call; only used to refresh the committed snapshot."""
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def build_airports(
    csv_bytes: Optional[bytes] = None,
    n_airports: int = 250,
) -> pl.DataFrame:
    """Build the silver `airports` reference table from raw OurAirports CSV.

    Used to refresh the committed snapshot. Demo / runtime callers should use
    `load_airports()` instead — it reads the snapshot and avoids the network.

    Args:
        csv_bytes: pre-fetched OurAirports CSV bytes. If None, fetches from URL.
        n_airports: how many airports to keep (sorted by size class, then name).
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


def load_airports(snapshot_path: Path = SNAPSHOT_PATH) -> pl.DataFrame:
    """Load the committed airports snapshot. No network call. Used by the demo seeder."""
    if not snapshot_path.exists():
        raise FileNotFoundError(
            f"Airports snapshot missing at {snapshot_path}. "
            f"Run `python -m src.data.aviation.airports --refresh` to rebuild."
        )
    return pl.read_parquet(snapshot_path)


def _refresh_snapshot(n_airports: int = 250) -> None:
    """Rebuild the snapshot from the live OurAirports CSV. Run this only when
    you intentionally want to update the committed reference data."""
    df = build_airports(n_airports=n_airports)
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(SNAPSHOT_PATH)
    print(f"refreshed {SNAPSHOT_PATH} — {len(df)} rows, {SNAPSHOT_PATH.stat().st_size} bytes")


if __name__ == "__main__":
    import sys

    if "--refresh" in sys.argv:
        _refresh_snapshot()
    else:
        print(load_airports())
