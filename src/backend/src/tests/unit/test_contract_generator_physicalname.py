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
