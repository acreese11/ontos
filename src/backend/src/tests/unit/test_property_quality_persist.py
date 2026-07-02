"""Phase 3: per-property (column-level) quality rules must persist.

Before this fix, `_create_schema_objects` built each SchemaProperty but never read
`prop_dict['quality']`, so column-level rules authored in the schema editor's Quality
tab were silently dropped on save. These tests pin that property-level rules now
persist as DataQualityCheckDb rows bound to their property via property_id, while
object-level rules keep persisting with property_id=None.
"""
import os
os.environ['TESTING'] = 'true'
os.environ['SKIP_STARTUP_TASKS'] = 'true'

import json
from pathlib import Path
from uuid import uuid4

from src.controller.data_contracts_manager import DataContractsManager
from src.db_models.data_contracts import (
    DataContractDb,
    DataQualityCheckDb,
    SchemaObjectDb,
    SchemaPropertyDb,
)


def _impl_str(name: str) -> str:
    return json.dumps({
        "check": {"function": "is_in_list", "arguments": {"column": "icao24", "allowed": ["A78A68"]}},
        "name": name,
        "criticality": "error",
    })


def _make_contract(db) -> DataContractDb:
    contract = DataContractDb(name="c_" + uuid4().hex[:6], version="1.0.0", status="active")
    db.add(contract)
    db.flush()
    return contract


class TestPropertyQualityPersist:
    def test_property_quality_persists_with_property_id(self, db_session):
        mgr = DataContractsManager(data_dir=Path("/tmp"))
        contract = _make_contract(db_session)
        schema_data = [{
            "name": "live_flights",
            "physicalName": "safe_skies.flight_ops.adsb_v2",
            "properties": [
                {
                    "name": "icao24", "logicalType": "string",
                    "quality": [{
                        "name": "icao24_in_list", "type": "custom", "engine": "dqx",
                        "implementation": _impl_str("icao24_in_list"),
                        "dimension": "validity", "severity": "error", "level": "property",
                    }],
                },
                {"name": "callsign", "logicalType": "string"},  # no quality
            ],
        }]
        mgr._create_schema_objects(db_session, contract.id, schema_data, current_user="t@safe-skies.demo")
        db_session.flush()

        checks = db_session.query(DataQualityCheckDb).filter(DataQualityCheckDb.property_id.isnot(None)).all()
        assert len(checks) == 1
        c = checks[0]
        assert c.name == "icao24_in_list"
        assert c.engine == "dqx"
        assert c.level == "property"
        assert c.implementation  # preserved (the executable part is NOT dropped)

        prop = db_session.query(SchemaPropertyDb).filter(SchemaPropertyDb.id == c.property_id).first()
        assert prop is not None and prop.name == "icao24"  # bound to the right column
        obj = db_session.query(SchemaObjectDb).filter(SchemaObjectDb.id == c.object_id).first()
        assert obj is not None and obj.name == "live_flights"

    def test_object_level_still_persists_without_property_id(self, db_session):
        mgr = DataContractsManager(data_dir=Path("/tmp"))
        contract = _make_contract(db_session)
        schema_data = [{
            "name": "tbl", "physicalName": "c.s.t",
            "quality": [{
                "name": "rowcount", "type": "custom", "engine": "dqx",
                "implementation": _impl_str("rowcount"), "dimension": "completeness", "severity": "warning",
            }],
            "properties": [{"name": "col1", "logicalType": "string"}],
        }]
        mgr._create_schema_objects(db_session, contract.id, schema_data, current_user="t@safe-skies.demo")
        db_session.flush()

        obj_checks = db_session.query(DataQualityCheckDb).filter(DataQualityCheckDb.property_id.is_(None)).all()
        assert any(c.name == "rowcount" and c.level == "object" for c in obj_checks)

    def test_dict_implementation_is_json_encoded_for_storage(self, db_session):
        # ODCS-import path may pass `implementation` as a dict; it must be JSON-encoded
        # into the Text column (the picker already emits a string, which passes through).
        mgr = DataContractsManager(data_dir=Path("/tmp"))
        contract = _make_contract(db_session)
        impl_dict = {
            "check": {"function": "is_not_null_and_not_empty", "arguments": {"column": "x"}},
            "name": "n", "criticality": "warn",
        }
        schema_data = [{
            "name": "t", "physicalName": "c.s.t",
            "properties": [{
                "name": "x", "logicalType": "string",
                "quality": [{"name": "n", "type": "custom", "engine": "dqx", "implementation": impl_dict, "level": "property"}],
            }],
        }]
        mgr._create_schema_objects(db_session, contract.id, schema_data, current_user="t@t")
        db_session.flush()

        c = db_session.query(DataQualityCheckDb).filter(DataQualityCheckDb.property_id.isnot(None)).first()
        assert c is not None and isinstance(c.implementation, str)
        assert json.loads(c.implementation)["check"]["function"] == "is_not_null_and_not_empty"


class TestUpdatePathDoesNotWipeColumnLevelChecks:
    """update_contract_with_relations's `qualityRules` handling used to delete ALL
    DataQualityCheckDb rows for a schema object (unscoped by property_id) whenever a
    payload included `qualityRules` - including any already-persisted column-level
    checks on that schema object. This is the realistic sequence: a prior request
    created + committed a column-level check (schema editor's per-column Quality
    tab), then a *later*, unrelated update sends only a `qualityRules` (object-level)
    change without re-sending `schema` at all - which the frontend commonly does for
    a partial update. Backported from upstream databrickslabs/ontos#528, which found
    and fixed the same bug independently.

    (Note: a single request that both creates a column-level check AND sets
    `qualityRules` does NOT reproduce this under this codebase's autoflush=False
    session config - the DELETE runs before the pending INSERT is flushed to the DB,
    so it has nothing to match. The real exposure is cross-request, once the
    column-level check is a durably committed row.)
    """

    def test_qualityRules_only_update_preserves_prior_column_level_checks(self, db_session):
        mgr = DataContractsManager(data_dir=Path("/tmp"))
        contract = _make_contract(db_session)

        # Step 1 (a prior request): create + durably persist a schema with a
        # column-level quality check.
        schema_data = [{
            "name": "live_flights",
            "physicalName": "safe_skies.flight_ops.adsb_v2",
            "properties": [{
                "name": "icao24", "logicalType": "string",
                "quality": [{
                    "name": "icao24_in_list", "type": "custom", "engine": "dqx",
                    "implementation": _impl_str("icao24_in_list"),
                    "dimension": "validity", "severity": "error", "level": "property",
                }],
            }],
        }]
        mgr._create_schema_objects(db_session, contract.id, schema_data, current_user="t@safe-skies.demo")
        db_session.commit()  # durably persisted, as it would be at the end of that prior request

        assert db_session.query(DataQualityCheckDb).filter(
            DataQualityCheckDb.property_id.isnot(None)
        ).count() == 1, "setup sanity check failed - column-level check wasn't persisted"

        # Step 2 (a later, unrelated request): update only `qualityRules`
        # (object-level) - no `schema` key at all, so _create_schema_objects never
        # runs in this request.
        update_payload = {"qualityRules": []}
        mgr.update_contract_with_relations(db_session, contract.id, update_payload, current_user="t@safe-skies.demo")
        db_session.flush()

        prop_checks = db_session.query(DataQualityCheckDb).filter(
            DataQualityCheckDb.property_id.isnot(None)
        ).all()
        assert len(prop_checks) == 1, (
            "column-level quality check was wiped by the unscoped qualityRules delete "
            "on the update path"
        )
        assert prop_checks[0].name == "icao24_in_list"
