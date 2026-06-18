"""Unit/integration tests for inline contract source-conformance validation.

``ContractValidationManager.run_source_validation`` diffs a contract's declared
schema (SchemaObjectDb / SchemaPropertyDb) against the LIVE Unity Catalog schema
read through the Databricks connector, then:

  * persists a ``DataContractValidationRunDb`` + one
    ``DataContractValidationResultDb`` per drift finding (check_type
    ``schema_drift``);
  * on any drift, fans a notification out to the contract owner + every product
    subscriber, reusing ``QualityManager.resolve_failure_recipients`` and
    ``NotificationsManager`` (the same trust loop as the DQX path).

The live UC read is the only external dependency; we mock it at the seam
(``ContractValidationManager._live_columns``) so the tests run offline. The
trust-loop collaborators are real instances bound to the test DB session.
"""
# Set test environment variables BEFORE any app imports
import os
os.environ['TESTING'] = 'true'
os.environ['SKIP_STARTUP_TASKS'] = 'true'

import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.controller.contract_validation_manager import ContractValidationManager, _types_match
from src.controller.quality_manager import QualityManager
from src.controller.entity_subscriptions_manager import EntitySubscriptionsManager
from src.controller.notifications_manager import NotificationsManager
from src.controller.data_products_manager import DataProductsManager
from src.db_models.data_contracts import (
    DataContractDb,
    DataContractTeamDb,
    SchemaObjectDb,
    SchemaPropertyDb,
)
from src.db_models.data_products import DataProductDb, OutputPortDb
from src.db_models.data_contract_validations import DataContractValidationRunDb
from src.db_models.notifications import NotificationDb
from src.models.entity_subscriptions import EntitySubscriptionCreate


OWNER_EMAIL = "ops-lead@safe-skies.demo"
SUBSCRIBER_A = "consumer-a@safe-skies.demo"
PHYSICAL = "safe_skies.flight_ops.adsb_v2"


# --- contract seeding -------------------------------------------------------

def _seed_contract(db, *, name="adsb_contract", columns=None):
    """Seed a contract with one schema object mapped to PHYSICAL.

    ``columns``: list of (name, logical_type, required). Defaults to a small
    ADS-B-like schema."""
    if columns is None:
        columns = [
            ("icao24", "string", True),
            ("alt_baro_ft", "integer", False),
            ("lat", "double", False),
        ]
    contract = DataContractDb(name=name, version="1.0.0", status="active")
    db.add(contract)
    db.flush()
    db.add(DataContractTeamDb(contract_id=contract.id, name="ops-lead", username=OWNER_EMAIL, role="owner"))
    obj = SchemaObjectDb(contract_id=contract.id, name="adsb", logical_type="object", physical_name=PHYSICAL)
    db.add(obj)
    db.flush()
    for cname, ctype, req in columns:
        db.add(SchemaPropertyDb(object_id=obj.id, name=cname, logical_type=ctype, required=req))
    db.flush()
    return contract


def _seed_product_with_subscriber(db, contract_id, email):
    product = DataProductDb(id=str(uuid4()), status="active", name="ADS-B Product", version="1.0.0")
    db.add(product)
    db.flush()
    db.add(OutputPortDb(product_id=product.id, name="current", version="1.0.0", contract_id=contract_id))
    db.flush()
    EntitySubscriptionsManager().subscribe(
        db, EntitySubscriptionCreate(entity_type="DataProduct", entity_id=product.id, subscriber_email=email)
    )
    db.flush()
    return product


# --- live-schema fakes ------------------------------------------------------

def _live(name, logical_type, required):
    return {"name": name, "logical_type": logical_type, "physical_type": logical_type, "required": required}


def _make_manager(db, *, live_columns):
    """ContractValidationManager with a real trust loop and a mocked live read.

    ``live_columns``: dict[name_lower] -> live col metadata (what UC returns)."""
    quality = QualityManager(
        notifications_manager=NotificationsManager(settings_manager=MagicMock()),
        entity_subscriptions_manager=EntitySubscriptionsManager(),
        data_products_manager=DataProductsManager(db=db),
    )
    mgr = ContractValidationManager(
        quality_manager=quality,
        notifications_manager=NotificationsManager(settings_manager=MagicMock()),
    )
    mgr._live_columns = MagicMock(return_value=live_columns)  # type: ignore[method-assign]
    return mgr


def _notifications_for(db, recipient):
    return db.query(NotificationDb).filter(NotificationDb.recipient == recipient).all()


# =========================================================================
# 1. Diff: clean run when declared matches live
# =========================================================================

class TestCleanRun:
    def test_matching_schema_passes_and_fires_no_notification(self, db_session):
        contract = _seed_contract(db_session)
        _seed_product_with_subscriber(db_session, contract.id, SUBSCRIBER_A)
        db_session.flush()

        live = {
            "icao24": _live("icao24", "string", True),
            "alt_baro_ft": _live("alt_baro_ft", "integer", False),
            "lat": _live("lat", "double", False),
        }
        mgr = _make_manager(db_session, live_columns=live)
        run = mgr.run_source_validation(db_session, contract_id=contract.id)

        assert run.status == "succeeded"
        assert run.checks_failed == 0
        assert run.score == 100.0
        # One passing result row for the object; no drift.
        assert all(r.passed for r in run.results)
        # No drift → no notifications.
        assert _notifications_for(db_session, OWNER_EMAIL) == []
        assert _notifications_for(db_session, SUBSCRIBER_A) == []


# =========================================================================
# 2. Diff: missing / extra / type-change drift findings
# =========================================================================

class TestDriftFindings:
    def test_missing_extra_and_type_change_detected(self, db_session):
        contract = _seed_contract(db_session)
        db_session.flush()

        # Live table: alt_baro_ft type changed integer->double, 'lat' dropped
        # (missing), 'squawk' added (extra).
        live = {
            "icao24": _live("icao24", "string", True),
            "alt_baro_ft": _live("alt_baro_ft", "double", False),
            "squawk": _live("squawk", "string", False),
        }
        mgr = _make_manager(db_session, live_columns=live)
        run = mgr.run_source_validation(db_session, contract_id=contract.id)

        kinds = {json.loads(r.details_json)["kind"] for r in run.results if not r.passed}
        assert "type_change" in kinds      # alt_baro_ft integer->double
        assert "missing_column" in kinds   # lat declared, absent live
        assert "extra_column" in kinds     # squawk live, undeclared
        assert run.checks_failed == 3
        assert run.status == "succeeded"

    def test_nullability_not_flagged_as_drift(self, db_session):
        # ODCS `required` is a DQX-enforced quality assertion, NOT physical nullability.
        # UC tables are nullable by default, so "contract required → table nullable" must
        # NOT be reported as schema drift (it was a false positive on every required column —
        # ~100% drift on healthy contracts). With only that difference, the run reports NO drift.
        contract = _seed_contract(db_session, columns=[("icao24", "string", True)])
        db_session.flush()
        live = {"icao24": _live("icao24", "string", False)}  # table nullable, type matches
        mgr = _make_manager(db_session, live_columns=live)
        run = mgr.run_source_validation(db_session, contract_id=contract.id)
        kinds = {json.loads(r.details_json)["kind"] for r in run.results if not r.passed}
        assert "nullability_change" not in kinds
        assert not [r for r in run.results if not r.passed]  # no drift at all


# =========================================================================
# 3. Persistence
# =========================================================================

class TestPersistence:
    def test_run_and_results_persisted(self, db_session):
        contract = _seed_contract(db_session)
        db_session.flush()
        live = {"icao24": _live("icao24", "string", True)}  # lat+alt missing
        mgr = _make_manager(db_session, live_columns=live)
        run = mgr.run_source_validation(db_session, contract_id=contract.id)

        persisted = (
            db_session.query(DataContractValidationRunDb)
            .filter(DataContractValidationRunDb.id == run.id)
            .first()
        )
        assert persisted is not None
        assert persisted.contract_id == contract.id
        assert len(persisted.results) >= 1
        assert all(r.check_type == "schema_drift" for r in persisted.results)


# =========================================================================
# 4. Trust loop: drift notifies owner + subscriber
# =========================================================================

class TestTrustLoop:
    def test_drift_notifies_owner_and_subscriber(self, db_session):
        contract = _seed_contract(db_session)
        _seed_product_with_subscriber(db_session, contract.id, SUBSCRIBER_A)
        db_session.flush()

        live = {"icao24": _live("icao24", "string", True), "alt_baro_ft": _live("alt_baro_ft", "double", False)}
        mgr = _make_manager(db_session, live_columns=live)
        mgr.run_source_validation(db_session, contract_id=contract.id)

        for email in (OWNER_EMAIL, SUBSCRIBER_A):
            notes = _notifications_for(db_session, email)
            assert len(notes) == 1, f"expected 1 notification for {email}, got {len(notes)}"
            n = notes[0]
            assert n.type == "warning"
            assert n.link == f"/data-contracts/{contract.id}"
            assert "adsb_contract" in (n.title or "")
            assert "schema drift" in (n.subtitle or "").lower()

    def test_notify_error_does_not_fail_validation(self, db_session):
        contract = _seed_contract(db_session)
        db_session.flush()
        live = {"icao24": _live("icao24", "string", True)}  # drift: lat+alt missing
        mgr = _make_manager(db_session, live_columns=live)
        mgr._notify_drift = MagicMock(side_effect=RuntimeError("notify boom"))  # type: ignore[method-assign]
        # Must not raise; the run is already committed.
        run = mgr.run_source_validation(db_session, contract_id=contract.id)
        assert run.status == "succeeded"
        mgr._notify_drift.assert_called_once()


# =========================================================================
# 5. Edge cases
# =========================================================================

class TestEdges:
    def test_unknown_contract_raises_value_error(self, db_session):
        mgr = _make_manager(db_session, live_columns={})
        with pytest.raises(ValueError):
            mgr.run_source_validation(db_session, contract_id=str(uuid4()))

    def test_object_without_physical_name_records_failure(self, db_session):
        contract = DataContractDb(name="no_phys", version="1.0.0", status="active")
        db_session.add(contract)
        db_session.flush()
        obj = SchemaObjectDb(contract_id=contract.id, name="orphan", logical_type="object", physical_name=None)
        db_session.add(obj)
        db_session.flush()
        mgr = _make_manager(db_session, live_columns={})
        run = mgr.run_source_validation(db_session, contract_id=contract.id)
        assert run.checks_failed == 1
        assert "no physical_name" in (run.results[0].message or "")


class TestTypesMatch:
    """Pure-function type comparison: parameterised forms match, distinct base
    types (the int→bigint widening drift) must NOT be masked by substring."""

    @pytest.mark.parametrize("declared,live", [
        ("decimal", "decimal(10,2)"),   # bare vs parameterised
        ("decimal(10,2)", "decimal"),   # reverse
        ("string", "string"),           # identical
        ("", "bigint"),                 # unknown declared side → never mismatch
        ("int", ""),                    # unknown live side
    ])
    def test_compatible_types_match(self, declared, live):
        assert _types_match(declared, live) is True

    @pytest.mark.parametrize("declared,live", [
        ("int", "bigint"),              # widening drift — the regression we fixed
        ("char", "varchar"),
        ("int", "tinyint"),
        ("float", "double"),
    ])
    def test_distinct_types_do_not_match(self, declared, live):
        assert _types_match(declared, live) is False
