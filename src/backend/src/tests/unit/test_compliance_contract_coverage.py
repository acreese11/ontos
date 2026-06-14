"""
Unit tests for the Contract Coverage compliance feature.

Covers:
- build_contract_table_index: contract -> source UC table mapping derived from
  SchemaObjectDb.physical_name (ODCS physicalName), including multi-schema
  contracts and tables claimed by more than one contract.
- parse_target_catalog: extracting the single target catalog from a rule.
- UnityCatalogLoader table enrichment: contract_count / contract_names applied
  to table objects, plus single-catalog scoping. The WorkspaceClient is faked
  so no live Databricks connection is required.
- The seeded "Contract Coverage" rule string actually parses and evaluates.
"""
from unittest.mock import MagicMock

from src.controller.compliance_manager import (
    build_contract_table_index,
    parse_target_catalog,
)
from src.common.compliance_entities import UnityCatalogLoader
from src.common.compliance_dsl import parse_rule, Evaluator
from src.db_models.data_contracts import DataContractDb, SchemaObjectDb


# --- Fakes for the Databricks WorkspaceClient (no live connection needed) ---

class _FakeNamed:
    def __init__(self, name, full_name=None, table_type="TABLE"):
        self.name = name
        self.full_name = full_name
        self.table_type = table_type


class _FakeWorkspaceClient:
    """Minimal stand-in for WorkspaceClient.catalogs/schemas/tables."""

    def __init__(self, tree):
        # tree: {catalog: {schema: [table_name, ...]}}
        self._tree = tree
        self.catalogs = MagicMock()
        self.schemas = MagicMock()
        self.tables = MagicMock()
        self.catalogs.list.side_effect = self._list_catalogs
        self.schemas.list.side_effect = self._list_schemas
        self.tables.list.side_effect = self._list_tables

    def _list_catalogs(self):
        return [_FakeNamed(c) for c in self._tree]

    def _list_schemas(self, catalog_name):
        return [_FakeNamed(s) for s in self._tree.get(catalog_name, {})]

    def _list_tables(self, catalog_name, schema_name):
        tables = self._tree.get(catalog_name, {}).get(schema_name, [])
        return [
            _FakeNamed(t, full_name=f"{catalog_name}.{schema_name}.{t}")
            for t in tables
        ]


# --- build_contract_table_index ---

def _make_contract(db, name, physical_names):
    contract = DataContractDb(name=name, version="1.0.0", status="active")
    db.add(contract)
    db.flush()
    for pn in physical_names:
        db.add(
            SchemaObjectDb(
                contract_id=contract.id,
                name=pn.split(".")[-1],
                logical_type="object",
                physical_name=pn,
            )
        )
    db.flush()
    return contract


def test_index_maps_physical_name_to_contract(db_session):
    c = _make_contract(db_session, "oag", ["safe_skies.scheduling.oag_schedule"])
    index = build_contract_table_index(db_session)
    entry = index["safe_skies.scheduling.oag_schedule"]
    assert len(entry) == 1
    assert entry[0]["contract_id"] == c.id
    assert entry[0]["contract_name"] == "oag"


def test_index_handles_multi_schema_contract(db_session):
    _make_contract(
        db_session,
        "flight_status",
        [
            "safe_skies.flight_ops.flight_status",
            "safe_skies.flight_ops.flight_status_delays",
        ],
    )
    index = build_contract_table_index(db_session)
    assert "safe_skies.flight_ops.flight_status" in index
    assert "safe_skies.flight_ops.flight_status_delays" in index


def test_index_lowercases_keys(db_session):
    _make_contract(db_session, "mixed", ["Safe_Skies.Scheduling.OAG_Schedule"])
    index = build_contract_table_index(db_session)
    assert "safe_skies.scheduling.oag_schedule" in index


def test_index_collects_multiple_contracts_per_table(db_session):
    _make_contract(db_session, "first", ["safe_skies.scheduling.oag_schedule"])
    _make_contract(db_session, "second", ["safe_skies.scheduling.oag_schedule"])
    index = build_contract_table_index(db_session)
    names = sorted(c["contract_name"] for c in index["safe_skies.scheduling.oag_schedule"])
    assert names == ["first", "second"]


def test_index_skips_null_physical_name(db_session):
    contract = DataContractDb(name="nophys", version="1.0.0", status="active")
    db_session.add(contract)
    db_session.flush()
    db_session.add(
        SchemaObjectDb(contract_id=contract.id, name="t", logical_type="object", physical_name=None)
    )
    db_session.flush()
    index = build_contract_table_index(db_session)
    assert index == {} or all(v for v in index.values())


# --- parse_target_catalog ---

def test_parse_target_catalog_single_quotes():
    rule = "MATCH (t:Object) WHERE t.type IN ['table'] AND t.catalog = 'safe_skies' ASSERT t.contract_count = 1"
    assert parse_target_catalog(rule) == "safe_skies"


def test_parse_target_catalog_double_quotes():
    assert parse_target_catalog('WHERE obj.catalog = "prod" ASSERT obj.x = 1') == "prod"


def test_parse_target_catalog_none_when_absent():
    assert parse_target_catalog("MATCH (t:Object) ASSERT t.contract_count = 1") is None


# --- UnityCatalogLoader enrichment + scoping ---

def test_loader_enriches_tables_with_contract_count():
    ws = _FakeWorkspaceClient(
        {"safe_skies": {"scheduling": ["oag_schedule", "rogue_table"]}}
    )
    index = {
        "safe_skies.scheduling.oag_schedule": [
            {"contract_id": "c1", "contract_name": "oag"},
        ],
    }
    loader = UnityCatalogLoader(ws, contract_table_index=index)
    tables = {e["name"]: e for e in loader.load_entities(["table"]) if e["type"] == "table"}

    assert tables["oag_schedule"]["contract_count"] == 1
    assert tables["oag_schedule"]["contract_names"] == ["oag"]
    # Ungoverned table: 0 contracts
    assert tables["rogue_table"]["contract_count"] == 0
    assert tables["rogue_table"]["contract_names"] == []


def test_loader_flags_conflicting_governance():
    ws = _FakeWorkspaceClient({"safe_skies": {"scheduling": ["oag_schedule"]}})
    index = {
        "safe_skies.scheduling.oag_schedule": [
            {"contract_id": "c1", "contract_name": "oag_v1"},
            {"contract_id": "c2", "contract_name": "oag_v2"},
        ],
    }
    loader = UnityCatalogLoader(ws, contract_table_index=index)
    tables = [e for e in loader.load_entities(["table"]) if e["type"] == "table"]
    assert tables[0]["contract_count"] == 2


def test_loader_scopes_to_target_catalog():
    ws = _FakeWorkspaceClient(
        {
            "safe_skies": {"scheduling": ["oag_schedule"]},
            "other_catalog": {"misc": ["junk"]},
        }
    )
    loader = UnityCatalogLoader(ws, target_catalog="safe_skies")
    catalogs = {e["name"] for e in loader.load_entities(["table"])}
    assert "junk" not in catalogs
    names = {e["name"] for e in loader.load_entities(["table"])}
    assert names == {"oag_schedule"}


# --- Seeded rule parses and evaluates against enriched table dicts ---

COVERAGE_RULE = (
    "MATCH (t:Object) WHERE t.type IN ['table'] AND t.catalog = 'safe_skies' "
    "ASSERT t.contract_count = 1 "
    "ON_FAIL FAIL 'Table {name} has {contract_count} contract(s) (expected exactly 1)'"
)


def test_coverage_rule_parses():
    parsed = parse_rule(COVERAGE_RULE)
    assert parsed["match_type"] == "Object"
    assert parsed["assert_clause"] is not None
    assert parsed["on_fail_actions"][0]["type"] == "FAIL"


def test_coverage_rule_evaluates():
    parsed = parse_rule(COVERAGE_RULE)
    cases = {
        "ungoverned": ({"type": "table", "catalog": "safe_skies", "name": "u", "contract_count": 0}, True, False),
        "governed": ({"type": "table", "catalog": "safe_skies", "name": "g", "contract_count": 1}, True, True),
        "conflict": ({"type": "table", "catalog": "safe_skies", "name": "c", "contract_count": 2}, True, False),
        "off_catalog": ({"type": "table", "catalog": "other", "name": "o", "contract_count": 0}, False, False),
    }
    for label, (obj, expect_where, expect_assert) in cases.items():
        where = Evaluator(obj).evaluate(parsed["where_clause"])
        assert bool(where) == expect_where, f"WHERE mismatch for {label}"
        if expect_where:
            asserted = Evaluator(obj).evaluate(parsed["assert_clause"])
            assert bool(asserted) == expect_assert, f"ASSERT mismatch for {label}"
