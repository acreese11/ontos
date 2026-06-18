"""The UC-table generator must stamp the full 3-level physicalName.

The generator drafts a contract FROM a Unity Catalog table, so it knows the real
catalog.schema.table — it must not let the LLM emit just the table name (which breaks
the link to the UC asset and the DQX job, which requires catalog.schema.table). This is
UC-scoped: `_finalize_contract` only runs in the UC-table generator, so non-UC contracts
(manual, other sources) are unaffected.
"""
import pytest

from src.controller.contract_generator_manager import _finalize_contract

CAT, SCH, TBL = "safe_skies", "flight_ops", "adsb_v2"
FQN = "safe_skies.flight_ops.adsb_v2"


def _finalize(contract):
    return _finalize_contract(contract, catalog=CAT, schema=SCH, table=TBL, warnings=[])


class TestPhysicalNameForcing:
    def test_table_only_name_is_qualified(self):
        c = _finalize({"schema": [{"name": "adsb_v2", "physicalName": "adsb_v2"}]})
        assert c["schema"][0]["physicalName"] == FQN

    def test_missing_physicalname_is_filled(self):
        c = _finalize({"schema": [{"name": "adsb_v2"}]})
        assert c["schema"][0]["physicalName"] == FQN

    def test_already_correct_is_idempotent(self):
        c = _finalize({"schema": [{"name": "adsb_v2", "physicalName": FQN}]})
        assert c["schema"][0]["physicalName"] == FQN

    def test_wrong_catalog_is_corrected_to_the_real_one(self):
        # LLM hallucinated a different catalog/schema — the generator's known location wins.
        c = _finalize({"schema": [{"name": "adsb_v2", "physicalName": "bronze.raw.adsb_v2"}]})
        assert c["schema"][0]["physicalName"] == FQN

    def test_physical_type_defaulted(self):
        c = _finalize({"schema": [{"name": "adsb_v2"}]})
        assert c["schema"][0]["physicalType"] == "table"

    def test_server_catalog_schema_stamped(self):
        c = _finalize({"schema": [{"name": "adsb_v2"}]})
        srv = c["servers"][0]
        assert srv["catalog"] == CAT and srv["schema"] == SCH and srv["type"] == "databricks"

    def test_multi_schema_qualifies_each_leaf(self):
        # Rare: LLM emits multiple schemas. Each leaf gets qualified with the source cat.schema.
        c = _finalize({"schema": [
            {"name": "a", "physicalName": "a"},
            {"name": "b", "physicalName": "other.ns.b"},
        ]})
        names = {s["physicalName"] for s in c["schema"]}
        assert names == {f"{CAT}.{SCH}.a", f"{CAT}.{SCH}.b"}


class TestLogicalTypeFromInspectedType:
    """Each column's logicalType/physicalType is derived deterministically from the inspected
    UC type (the same mapping source-conformance uses), so a fresh contract matches its table
    and complex types aren't mis-declared as 'string' by the LLM."""

    INSPECTED = [
        {"name": "_errors", "type_name": "ARRAY", "type_text": "array<struct<name:string>>"},
        {"name": "meta", "type_name": "STRUCT", "type_text": "struct<a:int>"},
        {"name": "tags", "type_name": "MAP", "type_text": "map<string,string>"},
        {"name": "alt_baro_ft", "type_name": "LONG", "type_text": "bigint"},
        {"name": "gs_kt", "type_name": "DOUBLE", "type_text": "double"},
        {"name": "icao24", "type_name": "STRING", "type_text": "string"},
        {"name": "ts_utc", "type_name": "TIMESTAMP", "type_text": "timestamp"},
    ]

    def _finalize_with_types(self, props):
        contract = {"schema": [{"name": "adsb_v2", "physicalName": "adsb_v2", "properties": props}]}
        return _finalize_contract(
            contract, catalog=CAT, schema=SCH, table=TBL, warnings=[],
            inspected_columns=self.INSPECTED,
        )

    def test_complex_types_corrected_from_string(self):
        # The LLM mis-typed the complex columns as 'string'; derivation fixes them.
        c = self._finalize_with_types([
            {"name": "_errors", "logicalType": "string"},
            {"name": "meta", "logicalType": "string"},
            {"name": "tags", "logicalType": "string"},
        ])
        props = {p["name"]: p for p in c["schema"][0]["properties"]}
        assert props["_errors"]["logicalType"] == "array"
        assert props["meta"]["logicalType"] == "object"
        assert props["tags"]["logicalType"] == "object"
        assert props["_errors"]["physicalType"] == "array<struct<name:string>>"

    def test_scalars_aligned_to_mapping(self):
        c = self._finalize_with_types([
            {"name": "alt_baro_ft", "logicalType": "number"},  # LLM said number; UC LONG → integer
            {"name": "gs_kt", "logicalType": "integer"},        # LLM said integer; UC DOUBLE → number
            {"name": "icao24", "logicalType": "string"},
            {"name": "ts_utc", "logicalType": "date"},          # LLM said date; UC TIMESTAMP → timestamp
        ])
        props = {p["name"]: p for p in c["schema"][0]["properties"]}
        assert props["alt_baro_ft"]["logicalType"] == "integer"
        assert props["gs_kt"]["logicalType"] == "number"
        assert props["icao24"]["logicalType"] == "string"
        assert props["ts_utc"]["logicalType"] == "timestamp"

    def test_unknown_column_left_untouched(self):
        # A property with no matching inspected column keeps the LLM's logicalType.
        c = self._finalize_with_types([{"name": "not_in_table", "logicalType": "string"}])
        props = {p["name"]: p for p in c["schema"][0]["properties"]}
        assert props["not_in_table"]["logicalType"] == "string"
