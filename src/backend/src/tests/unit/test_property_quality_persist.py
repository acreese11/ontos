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
