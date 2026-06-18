# Databricks notebook source
# MAGIC %md
# MAGIC # DQX Contract Validation — federated quality, made visible
# MAGIC
# MAGIC This notebook is the **reference federated quality pipeline**. It:
# MAGIC 1. Pulls an ODCS contract from Ontos
# MAGIC 2. Generates DQX rules **natively** from the contract (the contract *is* the ruleset)
# MAGIC 3. Applies the checks against the contract's target table
# MAGIC 4. Separates **errors** (hard failures → quarantine, drive the score) from **warnings**
# MAGIC    (surfaced as a signal, but do **not** fail the data)
# MAGIC 5. Posts a quality metric back to Ontos
# MAGIC
# MAGIC Every step displays what it's doing, so an audience can watch the contract become running
# MAGIC checks — and see exactly which rule flagged which rows.
# MAGIC
# MAGIC > Ontos is the system of record for contracts; the pipeline that produces the data is the
# MAGIC > right place to enforce quality (inline, near the source). Other engines (dbt+GE,
# MAGIC > Flink+cuelang, …) can play the same role — pull from `/odcs.yaml`, post to `/quality-items`.

# COMMAND ----------
# MAGIC %md ## Install DQX
# MAGIC We pin the latest DQX (the version carrying our upstreamed fix #1191). `%pip` here keeps the
# MAGIC notebook self-contained on serverless and is visible to the audience.

# COMMAND ----------
# MAGIC %pip install "databricks-labs-dqx>=0.15.0" datacontract-cli

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
# MAGIC %md ## Parameters
# MAGIC Passed as job parameters → notebook widgets. Run interactively by filling these in.

# COMMAND ----------
dbutils.widgets.text("contract_id", "")
dbutils.widgets.text("ontos_base_url", "")
dbutils.widgets.text("pipeline_id", "dqx_contract_validation")
dbutils.widgets.text("schema_index", "0")
dbutils.widgets.text("write_quarantine", "true")
dbutils.widgets.text("databricks_host", "")
dbutils.widgets.text("secrets_scope", "")
dbutils.widgets.text("client_id_key", "client_id")
dbutils.widgets.text("client_secret_key", "client_secret")

contract_id = dbutils.widgets.get("contract_id")
ontos_base_url = dbutils.widgets.get("ontos_base_url")
pipeline_id = dbutils.widgets.get("pipeline_id") or "dqx_contract_validation"
schema_index = int(dbutils.widgets.get("schema_index") or "0")
write_quarantine = (dbutils.widgets.get("write_quarantine") or "true").lower() == "true"
databricks_host = dbutils.widgets.get("databricks_host") or ""
secrets_scope = dbutils.widgets.get("secrets_scope")
client_id_key = dbutils.widgets.get("client_id_key") or "client_id"
client_secret_key = dbutils.widgets.get("client_secret_key") or "client_secret"

if not contract_id:
    raise ValueError("contract_id is required")
if not ontos_base_url:
    raise ValueError("ontos_base_url is required")
if not secrets_scope:
    raise ValueError("secrets_scope is required so the job can read the Ontos app's SP credentials")

print(f"contract_id     = {contract_id}")
print(f"ontos_base_url  = {ontos_base_url}")
print(f"pipeline_id     = {pipeline_id}")
print(f"schema_index    = {schema_index}")
print(f"write_quarantine= {write_quarantine}")

# COMMAND ----------
# MAGIC %md ## Setup — auth + Ontos HTTP helpers
# MAGIC The Databricks Apps proxy rejects bare job-runtime tokens; it accepts an OAuth M2M token
# MAGIC minted from the Ontos app's service principal (credentials read from a Secrets scope).

# COMMAND ----------
import base64
import json
import os
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, BooleanType
from databricks.sdk import WorkspaceClient


def _read_secret(ws: WorkspaceClient, scope: str, key: str) -> str:
    """Fetch a secret value via the SDK. Decodes the base64 payload Databricks returns."""
    secret = ws.secrets.get_secret(scope=scope, key=key)
    raw = getattr(secret, "value", None)
    if not raw:
        raise ValueError(f"Secret {scope}/{key} is empty or not readable by this identity.")
    return base64.b64decode(raw).decode("utf-8")


def _ontos_workspace_client(host: str, client_id: str, client_secret: str) -> WorkspaceClient:
    """WorkspaceClient that authenticates with the Ontos app's SP credentials (OAuth M2M)."""
    if not (host and client_id and client_secret):
        raise ValueError(
            "Need databricks_host plus resolvable secret-scope refs to authenticate to the "
            "Ontos app. Check the secrets scope + keys exist and are readable."
        )
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    return WorkspaceClient(host=host, client_id=client_id, client_secret=client_secret, auth_type="oauth-m2m")


def _bearer_token(ws: WorkspaceClient) -> str:
    headers = ws.config.authenticate() or {}
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise ValueError("Could not derive bearer token from WorkspaceClient config")
    return auth[7:]


def _ontos_get(base_url: str, path: str, token: str, *, accept: str = "application/json") -> bytes:
    url = f"{base_url.rstrip('/')}{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _ontos_post_json(base_url: str, path: str, token: str, body: Dict[str, Any]) -> None:
    url = f"{base_url.rstrip('/')}{path}"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=json.dumps(body).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"POST {path} failed: HTTP {e.code} — {detail}")


# `runtime_ws` = default job/notebook identity (Spark, UC reads, secrets, DQX).
# `apps_ws`    = OAuth M2M to the Ontos Apps proxy.
runtime_ws = WorkspaceClient()
apps_client_id = _read_secret(runtime_ws, secrets_scope, client_id_key)
apps_client_secret = _read_secret(runtime_ws, secrets_scope, client_secret_key)
apps_ws = _ontos_workspace_client(databricks_host, apps_client_id, apps_client_secret)
token = _bearer_token(apps_ws)
print("authenticated to the Ontos app proxy ✔")

# COMMAND ----------
# MAGIC %md ## Step 1 — Pull the contract from Ontos
# MAGIC We fetch the contract as JSON (for inspection) and YAML (the exact ODCS DQX will read).

# COMMAND ----------
contract = json.loads(_ontos_get(ontos_base_url, f"/api/data-contracts/{contract_id}/odcs.json", token))
yaml_text = _ontos_get(
    ontos_base_url, f"/api/data-contracts/{contract_id}/odcs.yaml", token, accept="application/x-yaml"
).decode("utf-8")

schemas = contract.get("schema") or []
if not schemas:
    raise ValueError(f"Contract {contract_id} has no schemas")
if schema_index >= len(schemas):
    raise ValueError(f"schema_index {schema_index} out of range (contract has {len(schemas)} schemas)")
schema = schemas[schema_index]
schema_name = schema.get("name")
physical_name = schema.get("physicalName")
if not physical_name or physical_name.count(".") != 2:
    raise ValueError(
        f"Schema {schema_name!r} has malformed physicalName {physical_name!r}; expected catalog.schema.table"
    )

print(f"contract.name = {contract.get('name')}   version = {contract.get('version')}")
print(f"schema        = {schema_name!r}  →  {physical_name}")

# The declared schema is the consumer's guarantee — show it so the audience sees what the
# contract promises (column, type, required) before we check whether the data delivers.
declared = [
    {"column": p.get("name"), "type": p.get("logicalType") or p.get("physicalType"), "required": p.get("required", False)}
    for p in (schema.get("properties") or [])
]
print(f"\ndeclared schema ({len(declared)} columns):")
# Explicit schema so all-None inference can't crash the cell.
_decl_schema = StructType([
    StructField("column", StringType()), StructField("type", StringType()),
    StructField("required", BooleanType()),
])
display(spark.createDataFrame(declared, schema=_decl_schema)) if declared else print("  (no properties)")

# COMMAND ----------
# MAGIC %md ## Step 2 — Resolve the validation strategy
# MAGIC Contracts may declare `validationStrategy` (full / time-window / cdf) via customProperties.

# COMMAND ----------
def _cp_value(c: Dict[str, Any], key: str, default: Optional[str] = None) -> Optional[str]:
    for cp in (c.get("customProperties") or []):
        if isinstance(cp, dict) and cp.get("property") == key:
            return cp.get("value")
    return default


strategy = {
    "strategy": _cp_value(contract, "validationStrategy", "full"),
    "column": _cp_value(contract, "validationColumn"),
    "lookback": _cp_value(contract, "validationLookback", "1h"),
}
print(f"strategy = {strategy}")

# COMMAND ----------
# MAGIC %md ## Step 3 — Generate DQX rules **natively** from the contract
# MAGIC DQX reads the ODCS contract directly. No translation layer — the rules ARE the contract.
# MAGIC We keep only the rules for the target schema (a contract can describe several).

# COMMAND ----------
from databricks.labs.dqx.profiler.generator import DQGenerator

with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
    f.write(yaml_text)
    contract_yaml_path = f.name

generator = DQGenerator(workspace_client=runtime_ws, spark=spark)
try:
    all_rules = generator.generate_rules_from_contract(
        contract_file=contract_yaml_path,
        generate_schema_validation=True,
        generate_predefined_rules=True,
        process_text_rules=False,
        # Contract is the consumer's OUTPUT GUARANTEE, not a mirror of every producer-side column.
        # Permissive mode: contract columns must exist with matching types, but extras + order are ok.
        strict_schema_validation=False,
    )
finally:
    try:
        os.unlink(contract_yaml_path)
    except OSError:
        pass

# DQGenerator emits rules for EVERY schema in the contract; this run validates one schema
# (schema_index). Keep only rules tagged for this schema (or untagged dataset-wide rules) —
# otherwise sibling-schema rules fire on the wrong table and flag every row.
if not schema_name:
    raise ValueError(f"Schema at index {schema_index} has no 'name'; cannot filter rules safely.")
rules = [r for r in all_rules if r.get("user_metadata", {}).get("schema") in (None, schema_name)]
explicit = sum(1 for r in rules if r.get("user_metadata", {}).get("rule_type") == "explicit")
print(
    f"generated {len(all_rules)} rules; {len(all_rules) - len(rules)} sibling-schema filtered out; "
    f"{len(rules)} apply ({explicit} are the contract's own custom quality rules)"
)

# Show the rules as a table — function, criticality, target columns, and whether it came from
# the contract's explicit quality block or was derived from a constraint.
def _rule_columns(check: Optional[dict]) -> str:
    args = (check or {}).get("arguments", {}) or {}
    cols = args.get("columns") or ([args.get("column")] if args.get("column") else [])
    return ", ".join(str(c) for c in cols if c is not None)

rule_view = [
    {
        "name": r.get("name"),
        "function": (r.get("check") or {}).get("function"),
        "criticality": r.get("criticality"),
        "columns": _rule_columns(r.get("check")),
        "source": r.get("user_metadata", {}).get("rule_type", "derived"),
    }
    for r in rules
]
# Explicit schema so a rule with an all-None field can't break inference.
_rule_schema = StructType([
    StructField("name", StringType()), StructField("function", StringType()),
    StructField("criticality", StringType()), StructField("columns", StringType()),
    StructField("source", StringType()),
])
display(spark.createDataFrame(rule_view, schema=_rule_schema)) if rule_view else print("no rules to apply")

# COMMAND ----------
# MAGIC %md ## Step 4 — Read the target table
# MAGIC Narrowed per the validation strategy (full scan unless a time-window is declared).

# COMMAND ----------
df = spark.read.table(physical_name)
if strategy["strategy"] == "time-window" and strategy.get("column"):
    col = strategy["column"]
    lookback = strategy.get("lookback") or "1h"
    n = int("".join(c for c in lookback if c.isdigit()) or "1")
    unit = "".join(c for c in lookback if c.isalpha()).lower() or "h"
    unit_seconds = {"h": 3600, "m": 60, "d": 86400}.get(unit, 3600)
    cutoff = datetime.now(timezone.utc).timestamp() - (n * unit_seconds)
    df = df.where(F.col(col) >= F.from_unixtime(F.lit(cutoff)).cast("timestamp"))
    print(f"time-window {lookback} on {col}")
else:
    print("full scan")

rows_before = df.count()
print(f"rows to validate: {rows_before}")
display(df.limit(20))

# COMMAND ----------
# MAGIC %md ## Step 5 — Apply DQX checks · errors vs warnings
# MAGIC We annotate every row with `_errors` / `_warnings` (no split yet), so we can see **which
# MAGIC rule flagged how many rows** — and separate hard failures (errors) from signals (warnings).
# MAGIC
# MAGIC **This is the fix:** errors drive the score and the quarantine; warnings are surfaced but
# MAGIC do **not** fail the data. (A `warning`-level rule like freshness shouldn't quarantine 100%
# MAGIC of rows just because a static feed is a few minutes old.)

# COMMAND ----------
from databricks.labs.dqx.engine import DQEngine

if not rules:
    print("no rules to apply; posting a clean metric and stopping")
    dbutils.notebook.exit("no-rules")

engine = DQEngine(runtime_ws)
checked = engine.apply_checks_by_metadata(df, rules)  # adds _errors, _warnings (array<struct>)
checked.cache()
rows_in = checked.count()

# DQX writes NULL (not []) into _errors/_warnings for a clean row — match DQX's own
# get_invalid() semantics (isNotNull) rather than size()>0.
error_rows = checked.where(F.col("_errors").isNotNull())
warn_rows = checked.where(F.col("_warnings").isNotNull())
error_count = error_rows.count()
warn_count = warn_rows.count()
pass_count = rows_in - error_count
score = (100.0 * pass_count / rows_in) if rows_in else 100.0

print(f"rows={rows_in}  errors(rows)={error_count}  warnings(rows)={warn_count}")
print(f"score (errors only) = {score:.2f}%   →   {pass_count}/{rows_in} pass")

# COMMAND ----------
# MAGIC %md #### Per-check breakdown — the money shot
# MAGIC Exactly which rule fired, at which severity, on how many rows.

# COMMAND ----------
err_break = (
    checked.where(F.col("_errors").isNotNull())
    .select(F.explode("_errors").alias("e"))
    .groupBy(F.col("e.name").alias("rule"), F.col("e.function").alias("function"))
    .count().withColumn("severity", F.lit("error")).orderBy(F.desc("count"))
)
warn_break = (
    checked.where(F.col("_warnings").isNotNull())
    .select(F.explode("_warnings").alias("w"))
    .groupBy(F.col("w.name").alias("rule"), F.col("w.function").alias("function"))
    .count().withColumn("severity", F.lit("warning")).orderBy(F.desc("count"))
)
print("ERRORS (hard failures → quarantine):")
display(err_break)
print("WARNINGS (surfaced, non-failing):")
display(warn_break)

# COMMAND ----------
# MAGIC %md ## Step 5b — Quarantine the failing (error) rows
# MAGIC Only **error**-level rows are quarantined. Valid rows (incl. warning-only rows) flow on.

# COMMAND ----------
if write_quarantine and error_count > 0:
    quarantine_name = f"{physical_name}_quarantine"
    (error_rows
        .withColumn("_validated_at", F.current_timestamp())
        .withColumn("_pipeline_id", F.lit(pipeline_id))
        .write.mode("append").saveAsTable(quarantine_name))
    print(f"quarantined {error_count} error rows → {quarantine_name}")
    display(error_rows.select("_errors", *[c for c in df.columns]).limit(20))
else:
    print(f"nothing quarantined (error_count={error_count}, write_quarantine={write_quarantine})")

# COMMAND ----------
# MAGIC %md ## Step 6 — Post the quality metric back to Ontos
# MAGIC The score is **error-driven** (the marketplace/trust signal). Warnings are reported in the
# MAGIC description so they're visible without failing the contract.

# COMMAND ----------
body = {
    "entity_id": contract_id,
    "entity_type": "data_contract",
    "title": f"{pipeline_id} run @ {datetime.now(timezone.utc).isoformat()}",
    "description": (
        f"DQX validation against schema {schema_name!r}: {pass_count}/{rows_in} passed "
        f"({error_count} error rows quarantined; {warn_count} rows carried warnings)."
    ),
    "dimension": "accuracy",
    "source": "dqx",
    "score_percent": round(score, 2),
    "checks_passed": pass_count,
    "checks_total": rows_in,
    "measured_at": datetime.now(timezone.utc).isoformat(),
}
_ontos_post_json(ontos_base_url, f"/api/entities/data_contract/{contract_id}/quality-items", token, body)
print("posted QualityItem ✔")
print(json.dumps(body, indent=2))
