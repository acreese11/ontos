"""Contract source-conformance (schema/metadata drift) validation.

This is the INLINE, synchronous counterpart to the remote Databricks job in
``src/workflows/data_contract_validation/data_contract_validation.py``. It
reuses that job's *drift semantics* (missing/extra columns, type changes,
nullability changes) but runs in-process so it works both locally and live:

  * declared schema comes from the contract's ``SchemaObjectDb`` /
    ``SchemaPropertyDb`` rows (name, logical/physical type, required), and each
    object's ``physical_name`` (e.g. ``safe_skies.flight_ops.adsb_v2``);
  * the LIVE schema is read from Unity Catalog via ``DatabricksConnector``
    (``get_asset_metadata`` → ``schema_info.columns``), on the caller's OBO
    workspace client when one is supplied;
  * the diff is persisted as a ``DataContractValidationRunDb`` plus one
    ``DataContractValidationResultDb`` per drift finding (check_type
    ``schema_drift``);
  * on any drift the trust loop fans out a notification to the contract owner
    + every product subscriber, reusing
    ``QualityManager.resolve_failure_recipients`` and ``NotificationsManager``.

Only ``schema_drift`` (schema + metadata) is in scope for v1. Access / SLA / DQ
check_types are intentionally NOT produced here (see the TODO in
``run_source_validation``); the remote job + the narrated Lakehouse Monitoring
path cover the statistical/SLA side.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from sqlalchemy.orm import Session

from src.common.logging import get_logger
from src.db_models.data_contracts import (
    DataContractDb,
    SchemaObjectDb,
    SchemaPropertyDb,
)
from src.db_models.data_contract_validations import (
    DataContractValidationRunDb,
    DataContractValidationResultDb,
)

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient
    from src.controller.quality_manager import QualityManager
    from src.controller.notifications_manager import NotificationsManager

logger = get_logger(__name__)


# Databricks system/rescue columns the connector already strips; mirror here so
# a contract that doesn't declare them is never flagged with spurious "extra".
_SYSTEM_COLUMNS = {"_rescued_data", "_metadata"}


def _normalize_type(value: Optional[str]) -> str:
    """Lower-case, strip a type for loose comparison.

    Logical types (the connector maps UC physical types to the same logical
    vocabulary the contract uses) compare cleanly; physical types are compared
    with substring tolerance by the caller. ``''`` means "type unknown" and is
    never treated as a mismatch."""
    return (value or "").strip().lower()


def _types_match(declared: str, live: str) -> bool:
    """True when declared and live types are compatible.

    Tolerant on purpose: an empty side (unknown type) never mismatches, and we
    accept substring overlap (e.g. declared ``decimal`` vs live ``decimal(10,2)``)
    so we only flag genuine changes (``int`` → ``double``)."""
    if not declared or not live:
        return True
    if declared == live:
        return True
    return declared in live or live in declared


class ContractValidationManager:
    """Inline source-conformance validation for data contracts.

    ``quality_manager`` is reused purely for recipient resolution
    (owner + subscribers); ``notifications_manager`` delivers the drift
    notification. Both optional so non-notifying / test paths can omit them."""

    def __init__(
        self,
        *,
        quality_manager: Optional["QualityManager"] = None,
        notifications_manager: Optional["NotificationsManager"] = None,
    ):
        self._quality_manager = quality_manager
        self._notifications_manager = notifications_manager

    # ── declared schema (contract side) ──────────────────────────────────

    @staticmethod
    def _declared_columns(obj: SchemaObjectDb) -> Dict[str, Dict[str, Any]]:
        """Map column-name(lower) → declared metadata for a schema object.

        Only top-level properties are considered (parent_property_id is None) —
        nested struct fields are out of scope for v1 drift."""
        declared: Dict[str, Dict[str, Any]] = {}
        for prop in (obj.properties or []):
            if getattr(prop, "parent_property_id", None):
                continue
            if not prop.name:
                continue
            key = prop.name.strip().lower()
            declared[key] = {
                "name": prop.name,
                "logical_type": _normalize_type(prop.logical_type),
                "physical_type": _normalize_type(prop.physical_type),
                # ODCS `required` is the contract's nullability assertion:
                # required == not-nullable.
                "required": bool(prop.required),
            }
        return declared

    # ── live schema (UC side) ────────────────────────────────────────────

    def _live_columns(
        self, *, physical_name: str, workspace_client: Optional["WorkspaceClient"]
    ) -> Dict[str, Dict[str, Any]]:
        """Read the live UC schema via the Databricks connector.

        Returns column-name(lower) → live metadata. Raises if the table can't be
        read (connector raises / returns no schema) so the caller can record a
        clear per-object error instead of a false "all columns missing"."""
        from src.connectors.databricks import DatabricksConnector

        connector = DatabricksConnector(workspace_client=workspace_client)
        metadata = connector.get_asset_metadata(physical_name)
        if metadata is None:
            raise RuntimeError(f"Table not found or not readable: {physical_name}")
        schema_info = getattr(metadata, "schema_info", None)
        if schema_info is None or not getattr(schema_info, "columns", None):
            raise RuntimeError(f"No schema available for table: {physical_name}")

        live: Dict[str, Dict[str, Any]] = {}
        for col in schema_info.columns:
            if not col.name:
                continue
            if col.name.lower() in _SYSTEM_COLUMNS:
                continue
            live[col.name.strip().lower()] = {
                "name": col.name,
                "logical_type": _normalize_type(col.logical_type),
                "physical_type": _normalize_type(col.data_type),
                # UC nullable=True ⇒ column is nullable.
                "required": not bool(getattr(col, "nullable", True)),
            }
        return live

    # ── diff ─────────────────────────────────────────────────────────────

    def _diff_object(
        self,
        *,
        object_name: str,
        physical_name: str,
        declared: Dict[str, Dict[str, Any]],
        live: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Diff one schema object's declared columns against its live columns.

        Returns a list of finding dicts, each shaped for a
        ``DataContractValidationResultDb`` row (kind, message, details). Drift
        kinds:
          * ``missing_column`` — declared in contract, absent in table
          * ``extra_column``   — present in table, not in contract
          * ``type_change``    — same column, incompatible type
          * ``nullability_change`` — same column, required/nullable flipped
        """
        findings: List[Dict[str, Any]] = []

        declared_keys = set(declared.keys())
        live_keys = set(live.keys())

        for key in sorted(declared_keys - live_keys):
            col = declared[key]
            findings.append({
                "kind": "missing_column",
                "message": f"{object_name}: column '{col['name']}' declared in contract but missing from table",
                "details": {
                    "object": object_name,
                    "physical_name": physical_name,
                    "column": col["name"],
                    "declared_type": col["logical_type"] or col["physical_type"] or None,
                },
            })

        for key in sorted(live_keys - declared_keys):
            col = live[key]
            findings.append({
                "kind": "extra_column",
                "message": f"{object_name}: column '{col['name']}' present in table but not declared in contract",
                "details": {
                    "object": object_name,
                    "physical_name": physical_name,
                    "column": col["name"],
                    "live_type": col["logical_type"] or col["physical_type"] or None,
                },
            })

        for key in sorted(declared_keys & live_keys):
            dcol = declared[key]
            lcol = live[key]
            # Prefer logical-type comparison (shared vocabulary); fall back to
            # physical when the contract didn't record a logical type.
            d_type = dcol["logical_type"] or dcol["physical_type"]
            l_type = lcol["logical_type"] or lcol["physical_type"]
            if not _types_match(d_type, l_type):
                findings.append({
                    "kind": "type_change",
                    "message": f"{object_name}: column '{dcol['name']}' type {d_type or '?'}→{l_type or '?'}",
                    "details": {
                        "object": object_name,
                        "physical_name": physical_name,
                        "column": dcol["name"],
                        "declared_type": d_type or None,
                        "live_type": l_type or None,
                    },
                })
            if dcol["required"] != lcol["required"]:
                findings.append({
                    "kind": "nullability_change",
                    "message": (
                        f"{object_name}: column '{dcol['name']}' nullability changed "
                        f"(contract {'required' if dcol['required'] else 'nullable'} → "
                        f"table {'required' if lcol['required'] else 'nullable'})"
                    ),
                    "details": {
                        "object": object_name,
                        "physical_name": physical_name,
                        "column": dcol["name"],
                        "declared_required": dcol["required"],
                        "live_required": lcol["required"],
                    },
                })

        return findings

    @staticmethod
    def _summarize(findings: List[Dict[str, Any]]) -> str:
        """One-line human summary, e.g. '2 schema drift(s): alt_baro_ft type INT→DOUBLE; +squawk'."""
        if not findings:
            return "No schema drift detected."
        parts: List[str] = []
        for f in findings[:3]:
            col = (f.get("details") or {}).get("column", "?")
            kind = f["kind"]
            if kind == "type_change":
                d = f["details"]
                parts.append(f"{col} type {(d.get('declared_type') or '?')}→{(d.get('live_type') or '?')}")
            elif kind == "missing_column":
                parts.append(f"-{col}")
            elif kind == "extra_column":
                parts.append(f"+{col}")
            elif kind == "nullability_change":
                parts.append(f"{col} nullability")
            else:
                parts.append(col)
        more = len(findings) - len(parts)
        tail = f"; +{more} more" if more > 0 else ""
        return f"{len(findings)} schema drift(s): " + "; ".join(parts) + tail

    # ── public entrypoint ────────────────────────────────────────────────

    def run_source_validation(
        self,
        db: Session,
        *,
        contract_id: str,
        user_token: Optional[str] = None,
        current_user: Optional[str] = None,
        workspace_client: Optional["WorkspaceClient"] = None,
    ) -> DataContractValidationRunDb:
        """Validate a contract's declared schema against its live UC tables.

        Diffs every mapped schema object (declared vs live), persists a run plus
        one result row per drift finding (check_type ``schema_drift``), and — on
        any drift — fires the owner+subscriber trust loop. Returns the persisted
        run (with ``results`` loaded).

        ``workspace_client`` (OBO) is preferred for the live read; ``user_token``
        is accepted and used to build one when no client is passed (mirrors the
        contract generator's OBO path). When neither is provided the connector
        falls back to the app service principal.

        TODO(v2): access / SLA / DQ check_types. SLA conformance should map
        Lakehouse Monitoring results back to ``data_contract_sla_properties``
        (freshness/volume/etc.) — see demo-4-maintain.md Appendix B.
        """
        contract: Optional[DataContractDb] = (
            db.query(DataContractDb).filter(DataContractDb.id == contract_id).first()
        )
        if contract is None:
            raise ValueError(f"Contract not found: {contract_id}")

        # Build an OBO workspace client from the raw token if the caller didn't
        # hand one in (route normally passes the client; LLM/CLI callers a token).
        if workspace_client is None and user_token:
            try:
                from databricks.sdk import WorkspaceClient
                from src.common.config import get_settings
                settings = get_settings()
                workspace_client = WorkspaceClient(host=settings.DATABRICKS_HOST, token=user_token)
            except Exception as e:
                logger.warning("Could not build OBO workspace client from token: %s", e)

        run = DataContractValidationRunDb(
            id=str(uuid.uuid4()),
            contract_id=contract_id,
            status="running",
            started_at=datetime.utcnow(),
            checks_passed=0,
            checks_failed=0,
            score=0.0,
        )
        db.add(run)
        db.flush()

        schema_objects: List[SchemaObjectDb] = list(contract.schema_objects or [])
        all_findings: List[Dict[str, Any]] = []
        result_rows: List[DataContractValidationResultDb] = []
        objects_checked = 0
        error_message: Optional[str] = None

        try:
            for obj in schema_objects:
                physical_name = (obj.physical_name or "").strip()
                if not physical_name:
                    # No mapping to a physical table → can't diff; record an
                    # informational (failing) result so the gap is visible.
                    result_rows.append(DataContractValidationResultDb(
                        id=str(uuid.uuid4()),
                        run_id=run.id,
                        contract_id=contract_id,
                        check_type="schema_drift",
                        passed=False,
                        message=f"{obj.name}: no physical_name mapping; cannot validate against source",
                        details_json=json.dumps({"object": obj.name, "reason": "missing_physical_name"}),
                        created_at=datetime.utcnow(),
                    ))
                    continue

                declared = self._declared_columns(obj)
                try:
                    live = self._live_columns(physical_name=physical_name, workspace_client=workspace_client)
                except Exception as e:
                    logger.warning("Live schema read failed for %s: %s", physical_name, e)
                    result_rows.append(DataContractValidationResultDb(
                        id=str(uuid.uuid4()),
                        run_id=run.id,
                        contract_id=contract_id,
                        check_type="schema_drift",
                        passed=False,
                        message=f"{obj.name}: failed to read live schema for {physical_name}: {e}",
                        details_json=json.dumps({
                            "object": obj.name,
                            "physical_name": physical_name,
                            "error": str(e),
                        }),
                        created_at=datetime.utcnow(),
                    ))
                    continue

                objects_checked += 1
                findings = self._diff_object(
                    object_name=obj.name,
                    physical_name=physical_name,
                    declared=declared,
                    live=live,
                )
                if findings:
                    all_findings.extend(findings)
                    for f in findings:
                        result_rows.append(DataContractValidationResultDb(
                            id=str(uuid.uuid4()),
                            run_id=run.id,
                            contract_id=contract_id,
                            check_type="schema_drift",
                            passed=False,
                            message=f["message"],
                            details_json=json.dumps({"kind": f["kind"], **f["details"]}),
                            created_at=datetime.utcnow(),
                        ))
                else:
                    # A clean object gets one passing result row so the run
                    # records what was actually verified.
                    result_rows.append(DataContractValidationResultDb(
                        id=str(uuid.uuid4()),
                        run_id=run.id,
                        contract_id=contract_id,
                        check_type="schema_drift",
                        passed=True,
                        message=f"{obj.name}: schema matches source ({len(declared)} columns)",
                        details_json=json.dumps({
                            "object": obj.name,
                            "physical_name": physical_name,
                            "columns": len(declared),
                        }),
                        created_at=datetime.utcnow(),
                    ))
        except Exception as e:  # defensive: never leave a run dangling
            logger.exception("Source validation crashed for contract %s", contract_id)
            error_message = str(e)

        for row in result_rows:
            db.add(row)

        checks_failed = sum(1 for r in result_rows if not r.passed)
        checks_passed = sum(1 for r in result_rows if r.passed)
        total = checks_passed + checks_failed
        score = round(100.0 * (checks_passed / total), 2) if total else 100.0

        run.checks_passed = checks_passed
        run.checks_failed = checks_failed
        run.score = score
        run.finished_at = datetime.utcnow()
        if error_message is not None:
            run.status = "failed"
            run.error_message = error_message
        else:
            run.status = "succeeded"

        db.commit()
        db.refresh(run)

        # Trust loop: any drift → notify owner + subscribers. A notify failure
        # must never fail the (already-committed) validation.
        if all_findings:
            try:
                self._notify_drift(db, contract=contract, findings=all_findings)
            except Exception:
                logger.exception("Schema-drift notification fan-out failed for contract %s", contract_id)

        return run

    # ── trust loop ────────────────────────────────────────────────────────

    def _notify_drift(
        self, db: Session, *, contract: DataContractDb, findings: List[Dict[str, Any]]
    ) -> int:
        """Fan a schema-drift finding out to owner + subscribers.

        Reuses ``QualityManager.resolve_failure_recipients`` (owner + product
        subscribers, deduped) and ``NotificationsManager.create_notification``.
        Returns the number of notifications created."""
        if self._quality_manager is None or self._notifications_manager is None:
            logger.debug("Trust-loop collaborators not wired; skipping drift fan-out")
            return 0

        recipients = self._quality_manager.resolve_failure_recipients(db, contract_id=contract.id)
        if not recipients:
            logger.info("No recipients resolved for schema drift on contract %s", contract.id)
            return 0

        from src.models.notifications import Notification, NotificationType

        contract_name = contract.name or contract.id
        subtitle = self._summarize(findings)
        link = f"/data-contracts/{contract.id}"
        description = (
            f"Source-conformance validation found schema drift on contract "
            f"'{contract_name}': {subtitle}. Review the contract and downstream impact."
        )

        created = 0
        for recipient in recipients:
            try:
                notification = Notification(
                    id=str(uuid.uuid4()),
                    type=NotificationType.WARNING,
                    title=f"Schema drift: {contract_name}",
                    subtitle=subtitle,
                    description=description,
                    link=link,
                    recipient=recipient,
                    created_at=datetime.utcnow(),
                    read=False,
                    can_delete=True,
                )
                self._notifications_manager.create_notification(notification, db)
                created += 1
            except Exception:
                logger.exception("Failed creating schema-drift notification for %s", recipient)
        db.commit()
        logger.info(
            "Schema-drift trust loop: contract=%s recipients=%d notifications=%d",
            contract.id, len(recipients), created,
        )
        return created

    # ── read path ──────────────────────────────────────────────────────────

    def get_latest_run(self, db: Session, *, contract_id: str) -> Optional[DataContractValidationRunDb]:
        """Most recent validation run (with results) for a contract, or None."""
        return (
            db.query(DataContractValidationRunDb)
            .filter(DataContractValidationRunDb.contract_id == contract_id)
            .order_by(DataContractValidationRunDb.started_at.desc())
            .first()
        )
