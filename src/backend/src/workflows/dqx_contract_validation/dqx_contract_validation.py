"""DQX Contract Validation — reference federated quality pipeline.

Pulls an ODCS contract from Ontos, generates DQX rules from it natively, runs the
checks against the contract's target table, writes failed rows to a quarantine
Delta table, and posts a summary back to Ontos's QualityItem ingestion endpoint.

This is positioned as a REFERENCE IMPLEMENTATION. Ontos is the system of record
for contracts; the pipeline that produces the data is the right place to enforce
quality (inline, near the source). Other engines (dbt+GE, Flink+cuelang, etc.)
can play the same role — they pull from /odcs.yaml and post to /quality-items.

Job parameters
  --contract_id        Ontos contract id (UUID)
  --ontos_base_url     Ontos host, e.g. https://ontos-<id>.<region>.azure.databricksapps.com
  --pipeline_id        Stable label for this pipeline (default "dqx_contract_validation")
  --schema_index       Which schema in the contract to validate (default 0). For multi-schema
                       contracts you'd run the job once per schema (or once per port).
  --write_quarantine   "true" / "false" — write failed rows to {table}_quarantine
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F

from databricks.sdk import WorkspaceClient


# ──────────────────────────────────────────────────────────────────────────────
# Workaround for databrickslabs/dqx#1168.
#
# DQX 0.14's contract_rules_generator.py has an UNCONDITIONAL top-of-file
# `from databricks.labs.dqx.llm.llm_engine import DQLLMEngine` — used only as
# a type annotation (`DQLLMEngine | None`). When [llm] extras aren't
# installed, that import raises ImportError, which a broad try/except in
# profiler/generator.py catches and turns into `DATACONTRACT_ENABLED = False`.
# DQGenerator.generate_rules_from_contract then raises MissingParameterError
# with a misleading "install datacontract-cli" message.
#
# We stub the module into sys.modules before any DQX import runs. The
# annotation resolves to the stub class; runtime never touches it because we
# call generate_rules_from_contract with process_text_rules=False (the only
# path that actually instantiates DQLLMEngine).
#
# Delete this once databrickslabs/dqx#1168 ships and we bump DQX past it.
# ──────────────────────────────────────────────────────────────────────────────
import types as _types  # noqa: E402
if "databricks.labs.dqx.llm.llm_engine" not in sys.modules:
    _llm_stub = _types.ModuleType("databricks.labs.dqx.llm.llm_engine")
    class _StubDQLLMEngine:  # noqa: N801
        """Stub for databrickslabs/dqx#1168 — never instantiated."""
    _llm_stub.DQLLMEngine = _StubDQLLMEngine
    sys.modules["databricks.labs.dqx.llm.llm_engine"] = _llm_stub


# ──────────────────────────────────────────────────────────────────────────────
# Auth + Ontos HTTP helpers
# ──────────────────────────────────────────────────────────────────────────────
def _read_secret(runtime_ws: WorkspaceClient, scope: str, key: str) -> str:
    """Fetch a secret value via the SDK. Decodes the base64 payload Databricks returns."""
    import base64
    secret = runtime_ws.secrets.get_secret(scope=scope, key=key)
    raw = getattr(secret, "value", None)
    if not raw:
        raise SystemExit(f"Secret {scope}/{key} is empty or not readable by this identity.")
    return base64.b64decode(raw).decode("utf-8")


def _ontos_workspace_client(host: str, client_id: str, client_secret: str) -> WorkspaceClient:
    """Build a WorkspaceClient that authenticates with the Ontos app's SP credentials.

    The Databricks Apps proxy at https://<app>.<region>.databricksapps.com rejects
    job-runtime tokens (which is what a bare ``WorkspaceClient()`` produces inside
    a job). It accepts OAuth M2M tokens minted from a service principal that has
    CAN_USE on the app.
    """
    if not (host and client_id and client_secret):
        raise SystemExit(
            "Job needs --databricks_host plus resolvable secret-scope refs to authenticate to "
            "the Ontos app. Check the secrets scope + keys exist and are readable."
        )
    return WorkspaceClient(
        host=host,
        client_id=client_id,
        client_secret=client_secret,
        auth_type="oauth-m2m",
    )


def _bearer_token(ws: WorkspaceClient) -> str:
    """Get the OAuth M2M bearer from the configured workspace client."""
    headers = ws.config.authenticate() or {}
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise SystemExit("Could not derive bearer token from WorkspaceClient config")
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
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        data=json.dumps(body).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"POST {path} failed: HTTP {e.code} — {body}")


# ──────────────────────────────────────────────────────────────────────────────
# Strategy resolution from contract customProperties
# ──────────────────────────────────────────────────────────────────────────────
def _cp_value(contract: Dict[str, Any], key: str, default: Optional[str] = None) -> Optional[str]:
    for cp in (contract.get("customProperties") or []):
        if isinstance(cp, dict) and cp.get("property") == key:
            return cp.get("value")
    return default


def resolve_strategy(contract: Dict[str, Any]) -> Dict[str, Any]:
    """Pick the validation strategy for this contract.

    Contract may declare customProperties:
      - validationStrategy: "full" | "time-window" | "cdf" (default: "full")
      - validationColumn: name of monotonic timestamp column (required for time-window)
      - validationLookback: e.g. "1h", "6h", "1d" (default "1h")
    """
    return {
        "strategy": _cp_value(contract, "validationStrategy", "full"),
        "column": _cp_value(contract, "validationColumn"),
        "lookback": _cp_value(contract, "validationLookback", "1h"),
    }


def build_dataframe(
    spark: SparkSession,
    physical_name: str,
    strategy: Dict[str, Any],
) -> DataFrame:
    """Read the target table, narrowed per the validation strategy."""
    df = spark.read.table(physical_name)
    if strategy["strategy"] == "time-window":
        col = strategy.get("column")
        lookback = strategy.get("lookback") or "1h"
        if not col:
            print(f"[strategy] time-window requested but no validationColumn; falling back to full scan")
            return df
        # Parse lookback (very simple: <n>h, <n>m, <n>d)
        n = int("".join(c for c in lookback if c.isdigit()) or "1")
        unit = "".join(c for c in lookback if c.isalpha()).lower() or "h"
        unit_seconds = {"h": 3600, "m": 60, "d": 86400}.get(unit, 3600)
        cutoff = datetime.now(timezone.utc).timestamp() - (n * unit_seconds)
        df = df.where(F.col(col) >= F.from_unixtime(F.lit(cutoff)).cast("timestamp"))
        print(f"[strategy] time-window {lookback} on {col} (cutoff ts={cutoff})")
    elif strategy["strategy"] == "cdf":
        # CDF support deferred — would use spark.read.format('delta').option('readChangeData', 'true')
        print(f"[strategy] cdf not yet implemented; falling back to full scan")
    else:
        print(f"[strategy] full scan")
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract_id", required=True)
    parser.add_argument("--ontos_base_url", required=True)
    parser.add_argument("--pipeline_id", default="dqx_contract_validation")
    parser.add_argument("--schema_index", type=int, default=0)
    parser.add_argument("--write_quarantine", default="true")
    parser.add_argument("--databricks_host", default="")
    # We fetch the M2M client_id/secret from a Databricks Secrets scope at
    # runtime rather than passing values through job parameters — secret-ref
    # substitution doesn't cascade through {{job.parameters.foo}} indirection,
    # so the secret values would arrive as literal "{{secrets/...}}" strings.
    parser.add_argument("--secrets_scope", default="")
    parser.add_argument("--client_id_key", default="client_id")
    parser.add_argument("--client_secret_key", default="client_secret")
    args = parser.parse_args()

    # Lazy DQX import so the job doesn't blow up if the dep is missing during a
    # smoke run; the failure mode is clearer when guarded.
    try:
        from databricks.labs.dqx.engine import DQEngine
        from databricks.labs.dqx.profiler.generator import DQGenerator
    except ImportError as e:
        raise SystemExit(
            "databricks-labs-dqx is required. Install >= 0.11.0 in the job environment.\n"
            f"Underlying ImportError: {e}"
        )

    spark = SparkSession.builder.appName(f"dqx_contract_validation_{args.contract_id}").getOrCreate()
    # Two workspace clients: one for talking to the Apps proxy (M2M OAuth — only
    # this token shape is accepted there), one with default runtime credentials
    # for everything else DQX might need (spark, UC reads, secrets, etc).
    runtime_ws = WorkspaceClient()
    if not args.secrets_scope:
        raise SystemExit("--secrets_scope is required so the job can read Apps SP credentials")
    apps_client_id = _read_secret(runtime_ws, args.secrets_scope, args.client_id_key)
    apps_client_secret = _read_secret(runtime_ws, args.secrets_scope, args.client_secret_key)
    apps_ws = _ontos_workspace_client(args.databricks_host, apps_client_id, apps_client_secret)
    token = _bearer_token(apps_ws)

    print(f"=== DQX contract validation ===")
    print(f"contract_id={args.contract_id}")
    print(f"ontos_base_url={args.ontos_base_url}")
    print(f"pipeline_id={args.pipeline_id}")

    # 1. Pull contract from Ontos (JSON for inspection, YAML for DQX).
    print(f"[1/6] Pulling contract from Ontos…")
    contract = json.loads(_ontos_get(
        args.ontos_base_url, f"/api/data-contracts/{args.contract_id}/odcs.json", token,
    ))
    yaml_text = _ontos_get(
        args.ontos_base_url, f"/api/data-contracts/{args.contract_id}/odcs.yaml", token,
        accept="application/x-yaml",
    ).decode("utf-8")

    schemas = contract.get("schema") or []
    if not schemas:
        raise SystemExit(f"Contract {args.contract_id} has no schemas")
    if args.schema_index >= len(schemas):
        raise SystemExit(f"schema_index {args.schema_index} out of range (contract has {len(schemas)} schemas)")
    schema = schemas[args.schema_index]
    physical_name = schema.get("physicalName")
    if not physical_name or physical_name.count(".") != 2:
        raise SystemExit(
            f"Schema {schema.get('name')!r} has malformed physicalName {physical_name!r}; "
            f"expected catalog.schema.table"
        )
    print(f"  contract.name={contract.get('name')} version={contract.get('version')}")
    print(f"  schema={schema.get('name')!r} → {physical_name}")

    # 2. Decide validation strategy.
    print(f"[2/6] Resolving validation strategy…")
    strategy = resolve_strategy(contract)
    print(f"  {strategy}")

    # 3. Hand the YAML to DQX to generate native rules.
    print(f"[3/6] Generating DQX rules from contract YAML…")
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yaml_text)
        contract_yaml_path = f.name
    try:
        generator = DQGenerator(workspace_client=runtime_ws, spark=spark)
        rules = generator.generate_rules_from_contract(
            contract_file=contract_yaml_path,
            generate_schema_validation=True,
            generate_predefined_rules=True,
            process_text_rules=False,
            # Contract is the consumer's OUTPUT GUARANTEE, not a mirror of every
            # producer-side column. Permissive mode requires the contract's
            # columns to exist with matching types, but allows extras and any
            # order — which is the right semantic for ODCS contracts.
            strict_schema_validation=False,
        )
    finally:
        try:
            os.unlink(contract_yaml_path)
        except OSError:
            pass

    # DQGenerator emits rules for EVERY schema in the contract, but this job
    # validates one schema at a time (selected by --schema_index). Without
    # filtering, rules tagged for sibling schemas fire on this table — their
    # required columns aren't here, so schema_validation flags every row and
    # the predefined-rule warnings drown the run. Keep only rules whose
    # user_metadata.schema matches the target schema name. Rules with no
    # schema tag (e.g. dataset-wide quality rules) are retained.
    target_schema_name = schema.get("name")
    total = len(rules)
    rules = [
        r for r in rules
        if (r.get("user_metadata", {}).get("schema") in (None, target_schema_name))
    ]
    skipped = total - len(rules)
    print(f"  generated {total} rules; {skipped} for sibling schemas filtered out, {len(rules)} apply")
    if not rules:
        print(f"  no rules to apply; exiting cleanly")
        return

    # 4. Read the target DataFrame.
    print(f"[4/6] Reading {physical_name}…")
    df = build_dataframe(spark, physical_name, strategy)
    rows_in = df.count()
    print(f"  rows to validate: {rows_in}")
    if rows_in == 0:
        print(f"  nothing to validate; posting an empty metric and exiting")
        _post_metric(args.ontos_base_url, args.contract_id, token, args.pipeline_id, schema.get("name"), 0, 0, 100.0)
        return

    # 5. Apply checks and split good vs bad rows.
    print(f"[5/6] Applying DQX checks…")
    engine = DQEngine(runtime_ws)
    good_df, bad_df = engine.apply_checks_by_metadata_and_split(df, rules)
    bad_count = bad_df.count()
    pass_count = rows_in - bad_count
    score = (100.0 * pass_count / rows_in) if rows_in else 100.0
    print(f"  pass={pass_count} fail={bad_count} score={score:.2f}%")

    if args.write_quarantine.lower() == "true" and bad_count > 0:
        quarantine_name = f"{physical_name}_quarantine"
        bad_df.withColumn("_validated_at", F.current_timestamp()) \
              .withColumn("_pipeline_id", F.lit(args.pipeline_id)) \
              .write.mode("append").saveAsTable(quarantine_name)
        print(f"  quarantined {bad_count} rows → {quarantine_name}")

    # 6. POST a quality metric back to Ontos.
    print(f"[6/6] Posting QualityItem to Ontos…")
    _post_metric(
        args.ontos_base_url,
        args.contract_id,
        token,
        args.pipeline_id,
        schema.get("name"),
        pass_count,
        rows_in,
        score,
    )
    print(f"  done.")


def _post_metric(
    base_url: str,
    contract_id: str,
    token: str,
    pipeline_id: str,
    schema_name: Optional[str],
    pass_count: int,
    total: int,
    score: float,
) -> None:
    """Post a single aggregated QualityItem for this run.

    Future refinement: emit one QualityItem per generated rule by inspecting the
    DQX result columns. For now we report the run-level pass rate which is the
    primary signal the marketplace and EntityQualityPanel surface.
    """
    body = {
        "entity_id": contract_id,
        "entity_type": "data_contract",
        "title": f"{pipeline_id} run @ {datetime.now(timezone.utc).isoformat()}",
        "description": f"DQX validation against schema {schema_name!r}: {pass_count}/{total} passed.",
        "dimension": "accuracy",
        "source": "dqx",
        "score_percent": round(score, 2),
        "checks_passed": pass_count,
        "checks_total": total,
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }
    _ontos_post_json(
        base_url,
        f"/api/entities/data_contract/{contract_id}/quality-items",
        token,
        body,
    )


if __name__ == "__main__":
    main()
