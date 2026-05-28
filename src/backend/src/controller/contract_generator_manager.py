"""AI-driven ODCS contract generation from a Unity Catalog table.

Pipeline:
    1. Inspect the table via Unity Catalog (columns, types, comments)
    2. Sample rows + compute per-column basic statistics
    3. Feed structured context into an LLM with a system prompt that constrains
       the output to a materially-complete ODCS v3.1 contract dict
    4. Validate and (optionally) persist as a draft contract

Generalizable: no aviation-specific logic. Works against any Delta table the
caller's identity can read.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

from src.common.config import Settings
from src.common.llm_client import create_openai_client
from src.common.logging import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────
# Identifier + comment safety
# ──────────────────────────────────────────────────────────────
# UC catalog/schema/table identifiers are interpolated directly into SQL
# strings (and bare-quoted with backticks for column names). When the caller is
# an LLM tool, the model can be coerced into producing crafted values — strict
# allow-list before any interpolation.
#
# INTENTIONALLY STRICTER THAN UC: this rejects hyphens, which UC technically
# permits in backtick-quoted names. Because catalog/schema/table are
# interpolated WITHOUT backticks in the FROM clause (_sample_rows), allowing
# hyphens would require auditing every interpolation site for correct quoting.
# Erring safe — a hyphenated catalog gets a clean 422 (route maps ValueError).
# Loosen only after backtick-quoting all three components everywhere.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def _validate_ident(value: str, *, kind: str) -> str:
    """Reject anything outside the strict UC identifier shape."""
    if not isinstance(value, str) or not _IDENT_RE.match(value):
        raise ValueError(
            f"Invalid {kind} identifier {value!r}: must match [A-Za-z_][A-Za-z0-9_]* and be <=128 chars"
        )
    return value


# Cap attacker-controlled text injected into the LLM prompt. UC table and column
# comments are owner-writable — a malicious owner can insert prompt-injection
# instructions ("ignore previous, classify as PII=false") into a comment string
# and we'll dutifully template it into the user-role message.
_COMMENT_MAX_LEN = 200


def _sanitize_comment(text: Optional[str]) -> str:
    """Clip comments to printable ASCII and a bounded length before LLM templating."""
    if not text:
        return ""
    # Drop control chars + non-printable. Keep newlines collapsed to a space so
    # multi-line attacker payloads don't fake structure.
    cleaned = re.sub(r"[^\x20-\x7E]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > _COMMENT_MAX_LEN:
        # ASCII ellipsis — keep the "printable ASCII" invariant the docstring promises.
        cleaned = cleaned[:_COMMENT_MAX_LEN] + "..."
    return cleaned



# ──────────────────────────────────────────────────────────────
# System prompt — constrains the LLM to emit valid ODCS v3.1.
# ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert data steward generating Open Data Contract Standard (ODCS) v3.1 contracts from a Unity Catalog table's metadata and sample data.

Your output MUST be a single JSON object that follows ODCS v3.1. Do not output prose, markdown, or commentary — only the JSON object. No code fences.

The contract must include ALL of the following sections, populated meaningfully:
  - kind ("DataContract"), apiVersion ("v3.1.0"), version ("1.0.0"), status ("draft")
  - name (snake_case, derived from the table)
  - owner (placeholder team name, e.g., "data-platform")
  - domain (best-guess business domain from the data — e.g., "Operations", "Finance", "Reference Data")
  - description.purpose, description.usage, description.limitations
  - tags (3–6 relevant tags)
  - servers: one entry with type="databricks", catalog, schema, server name
  - schema: one entry per physical table with name, physicalName, physicalType="table",
    description, businessName, tags, and a `properties` array with one entry per column
  - For each column in `properties`: name, logicalType (string/integer/number/boolean/date),
    physicalType (the source type, lowercased), description (write something meaningful inferred from
    the column name + sample values), required (true for FK-like or non-null-in-samples columns),
    classification ("Public"/"Internal"/"Restricted"), and where applicable: unique, examples (up to 3),
    pattern (regex for codes/IDs), min/max for numerics, enum for low-cardinality categoricals
  - qualityRules: 3–8 SPECIFIC, MEANINGFUL rules grounded in the sample data — uniqueness, completeness,
    range checks, regex/format, referential, freshness. Each rule has: name, description, rule (English
    or SQL-like), dimension (validity/completeness/uniqueness/freshness/consistency/accuracy),
    severity ("error" or "warning"), businessImpact ("low"/"medium"/"high"/"critical"). PREFER rules
    that match patterns visible in the samples.
  - roles: data-steward, domain-owner, consumer (each with role, description, access)
  - team: 2 members (owner + steward) with name/username/role
  - support: slack, email, docs channels
  - slaProperties: freshness, latency, retention, frequencyOfChange, availability
  - customProperties: dataClassification, containsPII (true/false based on column analysis),
    certificationLevel ("DRAFT" for AI-generated), ownerSlack, lifecyclePolicy

Be concise but materially complete. Quality rules in particular should be RULES YOU CAN JUSTIFY from the
sample data, not generic placeholders. If you see all values matching a regex, codify the regex.
If a column has 0 nulls in samples, mark it required. If a column has low cardinality, emit an enum.

OUTPUT: a single JSON object, nothing else."""


@dataclass
class GenerationResult:
    contract: Dict[str, Any]
    llm_model: str
    duration_seconds: float
    steps: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# UC inspection helpers
# ──────────────────────────────────────────────────────────────
def _run_sql(ws: WorkspaceClient, warehouse_id: str, statement: str, timeout_s: int = 30) -> List[List[Any]]:
    """Run a SQL statement and return rows (list of lists). Raises on error/timeout."""
    resp = ws.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=statement,
        wait_timeout="30s",
    )
    statement_id = resp.statement_id
    state = resp.status.state if resp.status else None
    deadline = time.time() + timeout_s
    while state in (StatementState.PENDING, StatementState.RUNNING) and time.time() < deadline:
        time.sleep(0.5)
        resp = ws.statement_execution.get_statement(statement_id=statement_id)
        state = resp.status.state if resp.status else None
    if state != StatementState.SUCCEEDED:
        err = resp.status.error.message if (resp.status and resp.status.error) else f"state={state}"
        raise RuntimeError(f"SQL failed: {err} ({statement[:120]}...)")
    result = resp.result
    if not result or not result.data_array:
        return []
    return result.data_array


def _inspect_columns(ws: WorkspaceClient, catalog: str, schema: str, table: str) -> List[Dict[str, Any]]:
    """Return column descriptors from Unity Catalog (no warehouse needed)."""
    full = f"{catalog}.{schema}.{table}"
    info = ws.tables.get(full_name=full)
    cols = []
    for c in (info.columns or []):
        cols.append({
            "name": c.name,
            "type_text": (c.type_text or "").lower(),
            "type_name": str(c.type_name) if c.type_name else "",
            "nullable": bool(c.nullable),
            "comment": c.comment or "",
            "position": c.position,
        })
    return cols


def _sample_rows(ws: WorkspaceClient, warehouse_id: str, catalog: str, schema: str, table: str, n: int = 20) -> List[List[Any]]:
    """Fetch up to `n` sample rows as list-of-lists, preserving column order."""
    return _run_sql(ws, warehouse_id, f"SELECT * FROM {catalog}.{schema}.{table} LIMIT {int(n)}")


def _column_stats(
    ws: WorkspaceClient,
    warehouse_id: str,
    catalog: str,
    schema: str,
    table: str,
    columns: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Per-column null %, distinct count, and top-3 sample values.

    Uses one SELECT with aggregate expressions per column to minimize round trips.
    """
    fq = f"{catalog}.{schema}.{table}"
    # First: row count + per-column null/distinct counts (one aggregate query).
    aggs = ["COUNT(*) AS _total"]
    for c in columns:
        col = c["name"]
        safe = f"`{col}`"
        aggs.append(f"SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END) AS `_null__{col}`")
        aggs.append(f"COUNT(DISTINCT {safe}) AS `_distinct__{col}`")
    try:
        rows = _run_sql(ws, warehouse_id, f"SELECT {', '.join(aggs)} FROM {fq} LIMIT 1")
    except Exception as e:
        logger.warning(f"Column-stats aggregate failed for {fq}: {e}")
        rows = []
    stats: Dict[str, Dict[str, Any]] = {c["name"]: {} for c in columns}
    if rows:
        row = rows[0]
        total = int(row[0]) if row[0] is not None else 0
        idx = 1
        for c in columns:
            nulls = int(row[idx]) if row[idx] is not None else 0
            distinct = int(row[idx + 1]) if row[idx + 1] is not None else 0
            stats[c["name"]] = {
                "row_count": total,
                "null_count": nulls,
                "null_pct": round(100 * nulls / total, 2) if total else None,
                "distinct_count": distinct,
            }
            idx += 2
    # Second: top-3 most common values per column (bounded query per column).
    for c in columns:
        col = c["name"]
        safe = f"`{col}`"
        try:
            top = _run_sql(ws, warehouse_id, (
                f"SELECT {safe}, COUNT(*) AS n FROM {fq} "
                f"WHERE {safe} IS NOT NULL GROUP BY {safe} ORDER BY n DESC LIMIT 3"
            ))
            stats[col]["top_values"] = [r[0] for r in top]
        except Exception as e:
            logger.debug(f"top_values failed for {fq}.{col}: {e}")
            stats[col]["top_values"] = []
    return stats


# ──────────────────────────────────────────────────────────────
# LLM call + parse
# ──────────────────────────────────────────────────────────────
def _build_user_prompt(
    catalog: str,
    schema: str,
    table: str,
    columns: List[Dict[str, Any]],
    sample_rows: List[List[Any]],
    stats: Dict[str, Dict[str, Any]],
    table_comment: str = "",
) -> str:
    """Assemble the context block the LLM sees.

    All attacker-controlled text (table comment, column comments) is bounded
    and stripped of control chars to keep prompt-injection from owner-writable
    UC metadata from steering the model.
    """
    safe_table_comment = _sanitize_comment(table_comment)
    lines = [
        f"Table: {catalog}.{schema}.{table}",
    ]
    if safe_table_comment:
        lines.append(f"Table comment: {safe_table_comment}")
    lines.append("")
    lines.append("Columns (name | source_type | nullable | comment):")
    for c in columns:
        # name/type_text are UC-derived (lower attacker control than comments,
        # since UC validates identifiers) but sanitized for consistency so no
        # owner-influenced metadata reaches the prompt unfiltered.
        safe_name = _sanitize_comment(c.get("name"))
        safe_type = _sanitize_comment(c.get("type_text"))
        safe_comment = _sanitize_comment(c.get("comment"))
        lines.append(f"  - {safe_name} | {safe_type} | {c['nullable']} | {safe_comment}")
    lines.append("")
    lines.append("Per-column statistics (from full table):")
    for c in columns:
        s = stats.get(c["name"], {})
        tv = s.get("top_values") or []
        tv_str = ", ".join(repr(v)[:50] for v in tv) if tv else "(none)"
        lines.append(
            f"  - {c['name']}: rows={s.get('row_count')}, nulls={s.get('null_count')} "
            f"({s.get('null_pct')}%), distinct={s.get('distinct_count')}, top_values=[{tv_str}]"
        )
    lines.append("")
    lines.append(f"Sample rows (first {len(sample_rows)}):")
    col_names = [c["name"] for c in columns]
    lines.append("  " + " | ".join(col_names))
    for row in sample_rows[:20]:
        cells = []
        for v in row:
            s = "NULL" if v is None else str(v)
            cells.append(s[:60])
        lines.append("  " + " | ".join(cells))
    lines.append("")
    lines.append(
        "Generate the ODCS v3.1 contract JSON for this table. Output ONLY the JSON object, no commentary, no code fences."
    )
    return "\n".join(lines)


def _extract_json(content: str) -> Dict[str, Any]:
    """Pull a JSON object out of an LLM response, tolerating code fences or trailing prose."""
    s = content.strip()
    # Strip markdown code fences if present
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    # Find first { ... } block via brace matching
    start = s.find("{")
    if start < 0:
        raise ValueError("No JSON object found in LLM response")
    depth = 0
    end = -1
    in_string = False
    escape = False
    for i, ch in enumerate(s[start:], start=start):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        raise ValueError("Unterminated JSON object in LLM response")
    return json.loads(s[start:end + 1])


# ──────────────────────────────────────────────────────────────
# Manager
# ──────────────────────────────────────────────────────────────
class ContractGeneratorManager:
    """Generate draft ODCS contracts from Unity Catalog tables via LLM."""

    def __init__(self, settings: Settings, contracts_manager=None, workspace_client: Optional[WorkspaceClient] = None):
        self.settings = settings
        self.contracts_manager = contracts_manager
        # When provided, this is the OBO workspace client built by the caller
        # (e.g., the LLM tool registry threads ctx.workspace_client through).
        # Without it, _ws() falls back to the app SP — fine for trusted
        # internal callers, NOT for end-user-initiated paths (privilege
        # escalation).
        self._explicit_ws = workspace_client

    def _ws(self) -> WorkspaceClient:
        if self._explicit_ws is not None:
            return self._explicit_ws
        # Fallback for internal/SP-trusted callers (CLI scripts, seeders).
        # Reuse the app's configured client (honors DATABRICKS_HOST/TOKEN, profile).
        from src.common.workspace_client import get_workspace_client
        return get_workspace_client(self.settings)

    def _warehouse_id(self) -> str:
        wid = self.settings.DATABRICKS_WAREHOUSE_ID
        if not wid:
            raise RuntimeError("DATABRICKS_WAREHOUSE_ID is required for sample / stats queries")
        return wid

    def generate(
        self,
        *,
        catalog: str,
        schema: str,
        table: str,
        sample_size: int = 20,
        user_token: Optional[str] = None,
    ) -> GenerationResult:
        """Inspect a UC table and produce a draft ODCS contract dict."""
        # Validate identifiers BEFORE any SQL interpolation or WorkspaceClient
        # call — these values come from a user (or LLM tool) and end up in
        # f-string SQL further down the pipeline.
        catalog = _validate_ident(catalog, kind="catalog")
        schema = _validate_ident(schema, kind="schema")
        table = _validate_ident(table, kind="table")

        t0 = time.time()
        steps: List[Dict[str, Any]] = []
        warnings: List[str] = []

        ws = self._ws()
        wid = self._warehouse_id()

        # 1. Inspect columns
        steps.append({"step": "inspect_columns", "started_at": time.time()})
        columns = _inspect_columns(ws, catalog, schema, table)
        steps[-1]["columns_found"] = len(columns)
        if not columns:
            raise RuntimeError(f"Table {catalog}.{schema}.{table} has no columns or doesn't exist")
        try:
            table_info = ws.tables.get(full_name=f"{catalog}.{schema}.{table}")
            table_comment = table_info.comment or ""
        except Exception:
            table_comment = ""

        # 2. Sample rows
        steps.append({"step": "sample_rows", "started_at": time.time()})
        try:
            sample = _sample_rows(ws, wid, catalog, schema, table, n=sample_size)
        except Exception as e:
            warnings.append(f"Sample failed: {e}")
            sample = []
        steps[-1]["rows_returned"] = len(sample)

        # 3. Per-column stats
        steps.append({"step": "column_stats", "started_at": time.time()})
        try:
            stats = _column_stats(ws, wid, catalog, schema, table, columns)
        except Exception as e:
            warnings.append(f"Column stats failed: {e}")
            stats = {c["name"]: {} for c in columns}
        steps[-1]["stats_computed"] = sum(1 for v in stats.values() if v)

        # 4. Build prompt + call LLM
        steps.append({"step": "llm_call", "started_at": time.time()})
        user_prompt = _build_user_prompt(catalog, schema, table, columns, sample, stats, table_comment)
        # If no user_token was supplied, borrow one from the already-authenticated
        # WorkspaceClient — its Config carries the active profile credentials.
        effective_token = user_token
        if not effective_token:
            try:
                headers = ws.config.authenticate() or {}
                auth = headers.get("Authorization", "")
                if auth.startswith("Bearer "):
                    effective_token = auth[7:]
            except Exception as e:
                warnings.append(f"Could not derive LLM token from workspace config: {e}")
        client = create_openai_client(self.settings, user_token=effective_token)
        endpoint = self.settings.LLM_ENDPOINT
        if not endpoint:
            raise RuntimeError("LLM_ENDPOINT is not configured")
        completion = client.chat.completions.create(
            model=endpoint,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=8192,
            temperature=0.2,
        )
        content = (completion.choices[0].message.content or "").strip() if completion.choices else ""
        steps[-1]["response_chars"] = len(content)
        if not content:
            raise RuntimeError("LLM returned empty response")

        # 5. Parse + minimal validation
        steps.append({"step": "parse_validate", "started_at": time.time()})
        try:
            contract = _extract_json(content)
        except Exception as e:
            raise RuntimeError(f"Failed to parse LLM output as JSON: {e}\nFirst 500 chars:\n{content[:500]}")

        # Ensure required top-level fields are present; fill conservative defaults
        contract.setdefault("kind", "DataContract")
        contract.setdefault("apiVersion", "v3.1.0")
        contract.setdefault("version", "1.0.0")
        contract.setdefault("status", "draft")
        if not contract.get("name"):
            contract["name"] = f"{table}".lower().replace(" ", "_")
        # Defensive normalization: the LLM occasionally emits list fields as
        # strings instead of dicts. Filter to dicts only and log warnings so
        # downstream persistence (which expects dict shapes) doesn't blow up.
        for field in ("schema", "qualityRules", "roles", "team", "support", "slaProperties", "customProperties"):
            raw = contract.get(field) or []
            if not isinstance(raw, list):
                contract[field] = []
                continue
            kept: List[Dict[str, Any]] = []
            dropped = 0
            for item in raw:
                if isinstance(item, dict):
                    kept.append(item)
                else:
                    dropped += 1
            if dropped:
                warnings.append(f"LLM emitted {dropped} non-dict entries in {field}; dropped")
            contract[field] = kept
        # Same drill one level deeper for schema[*].properties.
        for sch in contract.get("schema", []):
            props = sch.get("properties") or []
            if isinstance(props, list):
                sch["properties"] = [p for p in props if isinstance(p, dict)]

        # Force AI-draft markers on customProperties.
        cps = contract.get("customProperties") or []
        if not any(cp.get("property") == "generatedBy" for cp in cps):
            cps.append({"property": "generatedBy", "value": "ai", "description": "Contract drafted by AI from UC table inspection"})
        if not any(cp.get("property") == "sourceTable" for cp in cps):
            cps.append({"property": "sourceTable", "value": f"{catalog}.{schema}.{table}", "description": "Source table used for generation"})
        contract["customProperties"] = cps

        duration = time.time() - t0
        steps[-1]["duration_s"] = duration
        return GenerationResult(
            contract=contract,
            llm_model=endpoint,
            duration_seconds=duration,
            steps=steps,
            warnings=warnings,
        )

    @staticmethod
    def find_existing_for_table(db, catalog: str, schema: str, table: str) -> List[Dict[str, Any]]:
        """Return contracts whose schema includes the given physical table.

        Looks up ``SchemaObjectDb.physical_name == f"{catalog}.{schema}.{table}"`` across
        all contracts. A single contract may match multiple times (one row per matching
        schema entry) — we de-duplicate by contract id and return one row per contract.
        """
        from src.db_models.data_contracts import DataContractDb, SchemaObjectDb

        fq = f"{catalog}.{schema}.{table}"
        rows = (
            db.query(DataContractDb, SchemaObjectDb)
            .join(SchemaObjectDb, SchemaObjectDb.contract_id == DataContractDb.id)
            .filter(SchemaObjectDb.physical_name == fq)
            .all()
        )
        seen: Dict[str, Dict[str, Any]] = {}
        for contract, sch in rows:
            cid = str(contract.id)
            if cid in seen:
                continue
            seen[cid] = {
                "contract_id": cid,
                "name": contract.name,
                "version": contract.version,
                "status": contract.status,
                "matched_schema_name": sch.name,
            }
        return list(seen.values())

    def generate_and_save(
        self,
        *,
        db,
        catalog: str,
        schema: str,
        table: str,
        sample_size: int = 20,
        current_user: Optional[str] = None,
        user_token: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Generate a draft contract and persist it via DataContractsManager.

        If an existing contract already references this physical table (in any schema
        entry), no LLM call is made and the existing contract(s) are returned with
        ``already_exists=True``. Pass ``force=True`` to regenerate anyway.

        Returns a dict carrying the generated/existing contract, persisted contract id,
        and pipeline diagnostics suitable for UI display.
        """
        if not self.contracts_manager:
            raise RuntimeError("contracts_manager dependency not wired into ContractGeneratorManager")

        # Validate identifiers before they reach SQL interpolation or the
        # find-existing repo query (which also embeds the values in a SELECT).
        catalog = _validate_ident(catalog, kind="catalog")
        schema = _validate_ident(schema, kind="schema")
        table = _validate_ident(table, kind="table")

        # Existence check before the expensive LLM call.
        existing = self.find_existing_for_table(db, catalog, schema, table)
        if existing and not force:
            return {
                "already_exists": True,
                "existing": existing,
                "message": (
                    f"A contract for {catalog}.{schema}.{table} already exists "
                    f"(id={existing[0]['contract_id']}, name={existing[0]['name']!r}, "
                    f"status={existing[0]['status']!r}). Pass force=True to regenerate."
                ),
            }

        result = self.generate(catalog=catalog, schema=schema, table=table, sample_size=sample_size, user_token=user_token)
        created = self.contracts_manager.create_contract_with_relations(
            db=db,
            contract_data=result.contract,
            current_user=current_user,
            background_tasks=None,
        )
        return {
            "contract_id": str(created.id),
            "contract": result.contract,
            "llm_model": result.llm_model,
            "duration_seconds": result.duration_seconds,
            "steps": result.steps,
            "warnings": result.warnings,
        }
