# Databricks notebook source
# MAGIC %md
# MAGIC # DQX Contract Validation — federated quality, made visible
# MAGIC
# MAGIC This notebook is the **reference federated quality pipeline**. It:
# MAGIC 1. Pulls an ODCS contract from Ontos
# MAGIC 2. Generates DQX rules **natively** from the contract (the contract *is* the ruleset)
# MAGIC 3. For **every schema** in the contract, applies the checks against its table (full load)
# MAGIC 4. Separates **errors** (hard failures → quarantine, drive the score) from **warnings**
# MAGIC    (surfaced as a signal, but do **not** fail the data)
# MAGIC 5. Posts a quality metric back to Ontos — one per schema
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

# COMMAND ----------
dbutils.widgets.text("contract_id", "")
dbutils.widgets.text("ontos_base_url", "")
dbutils.widgets.text("pipeline_id", "dqx_contract_validation")
dbutils.widgets.text("write_quarantine", "true")
dbutils.widgets.text("databricks_host", "")
dbutils.widgets.text("secrets_scope", "")
dbutils.widgets.text("client_id_key", "client_id")
dbutils.widgets.text("client_secret_key", "client_secret")
# auth_mode: "run_as" (default) calls Ontos with the job's OWN Run-As identity — the
# realistic federated pattern (the producer's pipeline calls Ontos as itself; its Run-As
# principal needs CAN_USE on the Ontos app, no shared secret). A bare runtime token is
# rejected by the Apps proxy, so we exchange it for an app-audience OAuth token via the
# workspace OIDC token-exchange endpoint. Falls back to "app_sp" (OAuth M2M from an SP
# secret) if the exchange fails. Set "app_sp" to skip the Run-As attempt entirely.
dbutils.widgets.text("auth_mode", "run_as")
# app_client_id: the Ontos app's oauth2_app_client_id — the audience for the token
# exchange. The app passes its own DATABRICKS_CLIENT_ID. Required for auth_mode=run_as.
dbutils.widgets.text("app_client_id", "")

contract_id = dbutils.widgets.get("contract_id")
ontos_base_url = dbutils.widgets.get("ontos_base_url")
pipeline_id = dbutils.widgets.get("pipeline_id") or "dqx_contract_validation"
write_quarantine = (dbutils.widgets.get("write_quarantine") or "true").lower() == "true"
databricks_host = dbutils.widgets.get("databricks_host") or ""
secrets_scope = dbutils.widgets.get("secrets_scope")
client_id_key = dbutils.widgets.get("client_id_key") or "client_id"
client_secret_key = dbutils.widgets.get("client_secret_key") or "client_secret"
auth_mode = (dbutils.widgets.get("auth_mode") or "run_as").lower()
app_client_id = dbutils.widgets.get("app_client_id") or ""

if not contract_id:
    raise ValueError("contract_id is required")
if not ontos_base_url:
    raise ValueError("ontos_base_url is required")

print(f"contract_id      = {contract_id}")
print(f"ontos_base_url   = {ontos_base_url}")
print(f"pipeline_id      = {pipeline_id}")
print(f"write_quarantine = {write_quarantine}")
print(f"auth_mode        = {auth_mode}")

# COMMAND ----------
# MAGIC %md ## Setup — auth + Ontos HTTP helpers
# MAGIC `run_as`: call Ontos as the job's Run-As identity (needs CAN_USE on the app). A bare
# MAGIC job-runtime token is rejected by the Apps proxy (401), so we fall back to an OAuth M2M
# MAGIC token minted from an SP secret. **For the realistic pattern, run the job as a producer SP
# MAGIC that has CAN_USE on the Ontos app and point the secret at THAT SP — not the Ontos app's.**

# COMMAND ----------
import base64
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, BooleanType
from databricks.sdk import WorkspaceClient


def _read_secret(ws: WorkspaceClient, scope: str, key: str) -> str:
    secret = ws.secrets.get_secret(scope=scope, key=key)
    raw = getattr(secret, "value", None)
    if not raw:
        raise ValueError(f"Secret {scope}/{key} is empty or not readable by this identity.")
    return base64.b64decode(raw).decode("utf-8")


def _ontos_workspace_client(host: str, client_id: str, client_secret: str) -> WorkspaceClient:
    if not (host and client_id and client_secret):
        raise ValueError(
            "auth_mode=app_sp needs databricks_host + a readable secrets scope/keys to mint the "
            "OAuth M2M token. Check the scope + keys exist and are readable."
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


runtime_ws = WorkspaceClient()  # the job's Run-As identity (Spark, UC reads, secrets, DQX)


def _exchange_runas_for_app_token() -> str:
    """Exchange the job's Run-As internal token for an app-audience OAuth token — the
    realistic, secret-less federated pattern. The Run-As principal just needs CAN_USE on
    the Ontos app. A bare runtime token is rejected by the Apps proxy (401); the exchanged,
    app-audience token is accepted. (Databricks docs: dev-tools/databricks-apps/connect-local.)
    """
    ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
    subject_token = ctx.apiToken().get()
    host = runtime_ws.config.host.rstrip("/")
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": subject_token,
        "subject_token_type": "urn:databricks:params:oauth:token-type:personal-access-token",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "scope": "all-apis",
        "audience": app_client_id,
    }).encode()
    resp = urllib.request.urlopen(urllib.request.Request(f"{host}/oidc/v1/token", data=data, method="POST"))
    return json.loads(resp.read())["access_token"]


def _resolve_token() -> str:
    """Get a bearer the Ontos Apps proxy accepts. Prefer the job's Run-As identity (via
    token-exchange); fall back to OAuth M2M from an SP secret if that fails."""
    if auth_mode != "app_sp" and app_client_id:
        try:
            tok = _exchange_runas_for_app_token()
            _ontos_get(ontos_base_url, f"/api/data-contracts/{contract_id}/odcs.json", tok)  # probe
            print("authenticated to Ontos as the job's Run-As identity via token-exchange ✔")
            return tok
        except Exception as e:
            print(f"Run-As token-exchange failed ({e}); falling back to SP M2M…")
    elif auth_mode != "app_sp" and not app_client_id:
        print("auth_mode=run_as but no app_client_id provided; falling back to SP M2M…")
    cid = _read_secret(runtime_ws, secrets_scope, client_id_key)
    csec = _read_secret(runtime_ws, secrets_scope, client_secret_key)
    tok = _bearer_token(_ontos_workspace_client(databricks_host, cid, csec))
    print("authenticated to Ontos via SP M2M (fallback) ✔")
    return tok


token = _resolve_token()

# COMMAND ----------
# MAGIC %md ## Step 1 — Pull the contract from Ontos
# MAGIC JSON for inspection, YAML for DQX (the exact ODCS DQX reads).

# COMMAND ----------
contract = json.loads(_ontos_get(ontos_base_url, f"/api/data-contracts/{contract_id}/odcs.json", token))
yaml_text = _ontos_get(
    ontos_base_url, f"/api/data-contracts/{contract_id}/odcs.yaml", token, accept="application/x-yaml"
).decode("utf-8")

schemas = contract.get("schema") or []
if not schemas:
    raise ValueError(f"Contract {contract_id} has no schemas")
print(f"contract.name = {contract.get('name')}   version = {contract.get('version')}")
print(f"schemas to validate ({len(schemas)}):")
for s in schemas:
    print(f"  - {s.get('name')!r} → {s.get('physicalName')}")

# COMMAND ----------
# MAGIC %md ## Step 2 — Generate DQX rules **natively** from the contract
# MAGIC DQX reads the ODCS contract directly — no translation layer, the rules ARE the contract.
# MAGIC The generator emits rules for every schema; we filter per-schema in the loop below.

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
        # Contract is the consumer's OUTPUT GUARANTEE, not a mirror of every producer-side
        # column. Permissive: contract columns must exist with matching types; extras + order ok.
        strict_schema_validation=False,
    )
finally:
    try:
        os.unlink(contract_yaml_path)
    except OSError:
        pass

print(f"generated {len(all_rules)} rules across {len(schemas)} schema(s)")

# COMMAND ----------
# MAGIC %md ## Step 3 — Validate every schema (full load)
# MAGIC For each schema: filter its rules, read its table, apply checks, split errors vs warnings,
# MAGIC show the per-check breakdown, quarantine error rows, and post a quality metric to Ontos.

# COMMAND ----------
from databricks.labs.dqx.engine import DQEngine

_RULE_SCHEMA = StructType([
    StructField("name", StringType()), StructField("function", StringType()),
    StructField("criticality", StringType()), StructField("columns", StringType()),
    StructField("source", StringType()),
])


def _rule_columns(check: Optional[dict]) -> str:
    args = (check or {}).get("arguments", {}) or {}
    cols = args.get("columns") or ([args.get("column")] if args.get("column") else [])
    return ", ".join(str(c) for c in cols if c is not None)


def _post_metric(schema_name, physical_name, pass_count, rows_in, score, error_count, warn_count):
    body = {
        "entity_id": contract_id,
        "entity_type": "data_contract",
        "title": f"{pipeline_id} run @ {datetime.now(timezone.utc).isoformat()}",
        "description": (
            f"DQX validation of {physical_name} (schema {schema_name!r}): {pass_count}/{rows_in} "
            f"passed ({error_count} error rows quarantined; {warn_count} rows carried warnings)."
        ),
        "dimension": "accuracy",
        "source": "dqx",
        "score_percent": round(score, 2),
        "checks_passed": pass_count,
        "checks_total": rows_in,
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }
    _ontos_post_json(ontos_base_url, f"/api/entities/data_contract/{contract_id}/quality-items", token, body)


engine = DQEngine(runtime_ws)
summary = []

for sch in schemas:
    schema_name = sch.get("name")
    physical_name = sch.get("physicalName")
    print(f"\n{'='*70}\nSCHEMA {schema_name!r} → {physical_name}\n{'='*70}")
    if not physical_name or physical_name.count(".") != 2:
        print(f"  ⚠️ skipping: physicalName {physical_name!r} is not a 3-level UC name")
        summary.append({"schema": schema_name, "physical_name": physical_name, "status": "skipped (not UC)"})
        continue

    # Keep rules tagged for this schema (or untagged dataset-wide rules).
    rules = [r for r in all_rules if r.get("user_metadata", {}).get("schema") in (None, schema_name)]
    explicit = sum(1 for r in rules if r.get("user_metadata", {}).get("rule_type") == "explicit")
    print(f"  {len(rules)} rules apply ({explicit} from the contract's custom quality rules)")
    if not rules:
        print("  no rules to apply; skipping")
        summary.append({"schema": schema_name, "physical_name": physical_name, "status": "no rules"})
        continue

    rule_view = [{
        "name": r.get("name"),
        "function": (r.get("check") or {}).get("function"),
        "criticality": r.get("criticality"),
        "columns": _rule_columns(r.get("check")),
        "source": r.get("user_metadata", {}).get("rule_type", "derived"),
    } for r in rules]
    display(spark.createDataFrame(rule_view, schema=_RULE_SCHEMA))

    # Full load (no validation strategy — always the whole table).
    df = spark.read.table(physical_name)
    checked = engine.apply_checks_by_metadata(df, rules)  # adds _errors, _warnings
    rows_in = checked.count()
    error_rows = checked.where(F.col("_errors").isNotNull())
    warn_rows = checked.where(F.col("_warnings").isNotNull())
    error_count = error_rows.count()
    warn_count = warn_rows.count()
    pass_count = rows_in - error_count
    score = (100.0 * pass_count / rows_in) if rows_in else 100.0
    print(f"  rows={rows_in}  error_rows={error_count}  warning_rows={warn_count}  score={score:.2f}%")

    # Per-check breakdown — the money shot.
    err_break = (checked.where(F.col("_errors").isNotNull())
                 .select(F.explode("_errors").alias("e"))
                 .groupBy(F.col("e.name").alias("rule"), F.col("e.function").alias("function"))
                 .count().withColumn("severity", F.lit("error")).orderBy(F.desc("count")))
    warn_break = (checked.where(F.col("_warnings").isNotNull())
                  .select(F.explode("_warnings").alias("w"))
                  .groupBy(F.col("w.name").alias("rule"), F.col("w.function").alias("function"))
                  .count().withColumn("severity", F.lit("warning")).orderBy(F.desc("count")))
    print("  ERRORS (hard failures → quarantine):")
    display(err_break)
    print("  WARNINGS (surfaced, non-failing):")
    display(warn_break)

    # Example failing records — the actual bad rows + which rule(s) they broke. This is
    # the demo's payoff: you can see the negative altitude / malformed code, not just a count.
    if error_count > 0:
        print(f"  example FAILING records ({min(error_count, 10)} of {error_count}) — tagged with the rule they broke:")
        display(error_rows.select(
            F.expr("transform(_errors, e -> e.name)").alias("failed_rules"),
            *df.columns,
        ).limit(10))
    if warn_count > 0:
        print(f"  example WARNED records ({min(warn_count, 5)} of {warn_count}):")
        display(warn_rows.select(
            F.expr("transform(_warnings, w -> w.name)").alias("warned_rules"),
            *df.columns,
        ).limit(5))

    if write_quarantine and error_count > 0:
        quarantine_name = f"{physical_name}_quarantine"
        (error_rows.withColumn("_validated_at", F.current_timestamp())
                   .withColumn("_pipeline_id", F.lit(pipeline_id))
                   .write.mode("append").saveAsTable(quarantine_name))
        print(f"  quarantined {error_count} error rows → {quarantine_name}")

    _post_metric(schema_name, physical_name, pass_count, rows_in, score, error_count, warn_count)
    print("  posted QualityItem ✔")
    summary.append({
        "schema": schema_name, "physical_name": physical_name, "rows": rows_in,
        "errors": error_count, "warnings": warn_count, "score_percent": round(score, 2),
    })

# COMMAND ----------
# MAGIC %md ## Summary — all schemas

# COMMAND ----------
print(json.dumps(summary, indent=2))
