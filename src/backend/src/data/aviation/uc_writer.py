"""Upload Parquet to a UC Volume and materialize Delta tables in the safe_skies catalog.

Workflow per table:
    1. Write the Polars DataFrame to a local temp Parquet
    2. Upload it to `/Volumes/areese_demo_catalog/ontos/ontos_volume/safe_skies_seed/<schema>/<table>.parquet`
    3. Execute `CREATE OR REPLACE TABLE safe_skies.<schema>.<table>
                  AS SELECT * FROM read_files('<volume_path>', format=>'parquet')`
       via the Statement Execution API on the configured warehouse.
"""
from __future__ import annotations

import io
import time
from dataclasses import dataclass
from typing import Optional

import polars as pl
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

VOLUME_BASE = "/Volumes/areese_demo_catalog/ontos/ontos_volume/safe_skies_seed"


@dataclass
class WriteResult:
    schema: str
    table: str
    rows: int
    volume_path: str
    state: str
    error: Optional[str] = None


def upload_parquet_to_volume(
    w: WorkspaceClient,
    df: pl.DataFrame,
    schema: str,
    table: str,
) -> str:
    """Upload `df` as Parquet to the configured UC Volume path and return that path."""
    buf = io.BytesIO()
    df.write_parquet(buf, compression="snappy")
    buf.seek(0)

    volume_path = f"{VOLUME_BASE}/{schema}/{table}.parquet"
    # Files API expects bytes
    w.files.upload(file_path=volume_path, contents=buf, overwrite=True)
    return volume_path


def materialize_delta_from_parquet(
    w: WorkspaceClient,
    warehouse_id: str,
    catalog: str,
    schema: str,
    table: str,
    volume_path: str,
) -> str:
    """Run CREATE OR REPLACE TABLE ... AS SELECT FROM read_files via the SQL warehouse."""
    sql = (
        f"CREATE OR REPLACE TABLE {catalog}.{schema}.{table} "
        f"AS SELECT * FROM read_files('{volume_path}', format => 'parquet')"
    )
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=sql,
        wait_timeout="50s",
    )
    state = resp.status.state.value if resp.status and resp.status.state else "UNKNOWN"
    # Poll if not finished
    sid = resp.statement_id
    while state in ("PENDING", "RUNNING"):
        time.sleep(2)
        resp = w.statement_execution.get_statement(sid)
        state = resp.status.state.value if resp.status and resp.status.state else "UNKNOWN"

    return state


def write_table(
    w: WorkspaceClient,
    warehouse_id: str,
    df: pl.DataFrame,
    schema: str,
    table: str,
    catalog: str = "safe_skies",
) -> WriteResult:
    """End-to-end: upload Parquet + materialize Delta table."""
    if df.height == 0:
        return WriteResult(schema, table, 0, "", "SKIPPED", "empty df")

    try:
        path = upload_parquet_to_volume(w, df, schema, table)
        state = materialize_delta_from_parquet(w, warehouse_id, catalog, schema, table, path)
        return WriteResult(schema, table, df.height, path, state)
    except Exception as e:
        return WriteResult(schema, table, df.height, "", "FAILED", str(e))


def ensure_seed_dirs(w: WorkspaceClient, schemas: list[str]) -> None:
    """Pre-create per-schema directories under the seed volume."""
    for s in schemas:
        try:
            w.files.create_directory(f"{VOLUME_BASE}/{s}")
        except Exception:
            # already exists is fine
            pass
