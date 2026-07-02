"""Unit tests for the DQX check catalog + ODCS-quality envelope (``common/dqx_catalog``).

The headline test is the **Phase-1 correctness gate**: the envelope's
``sql_expression_implementation`` must reproduce the aviation seed's hand-authored,
known-DQX-runnable ``implementation`` byte-for-byte — proving we emit exactly what
DQX's ``DataContractRulesGenerator`` already consumes before any surface depends on it.
"""
import os
os.environ['TESTING'] = 'true'
os.environ['SKIP_STARTUP_TASKS'] = 'true'

from src.common.dqx_catalog import (
    to_criticality,
    build_implementation,
    sql_expression_implementation,
    to_display,
    catalog,
    serialize_catalog,
    check_to_sql_predicate,
    CHECK_CATALOG,
    CONSTRAINT_DERIVED_FUNCTIONS,
)


class TestCriticality:
    def test_mapping(self):
        assert to_criticality("error") == "error"
        assert to_criticality("warning") == "warn"
        assert to_criticality("WARNING") == "warn"      # case-insensitive
        assert to_criticality(None) == "error"          # default
        assert to_criticality("nonsense") == "error"    # unknown → default


class TestEnvelopeReproducesSeed:
    """The aviation seed's `_qrule` emits the known-good DQX-runnable shape; the
    envelope must reproduce it exactly so authored/generated rules match."""

    def test_sql_expression_implementation_matches_qrule(self):
        from src.data.aviation.definitions import _qrule
        rule = _qrule(
            "icao24_format",
            "icao24 must be a 6-character uppercase hex transponder address",
            rule="icao24 matches '^[0-9A-F]{6}$'",
            sql_expr="icao24 rlike '^[0-9A-F]{6}$'",
            dimension="validity",
            business_impact="critical",
        )
        expected = sql_expression_implementation(
            "icao24 rlike '^[0-9A-F]{6}$'",
            "icao24 must be a 6-character uppercase hex transponder address",
            name="icao24_format",
            criticality="error",
        )
        assert rule["implementation"] == expected
        assert rule["type"] == "custom"
        assert rule["engine"] == "dqx"

    def test_warning_severity_maps_to_warn(self):
        from src.data.aviation.definitions import _qrule
        rule = _qrule(
            "vert_rate_plausible",
            "Vertical rate beyond +/-10,000 fpm is implausible",
            rule="abs(vert_rate_fpm) <= 10000",
            severity="warning",
            dimension="validity",
        )
        expected_crit = to_criticality("warning")
        assert expected_crit == "warn"  # pin the literal, not just both sides of the mapping
        assert rule["implementation"]["criticality"] == expected_crit

    def test_expression_defaults_to_rule_when_no_sql_expr(self):
        # _qrule uses `sql_expr or rule`; the envelope reproduces whatever expression it's given.
        from src.data.aviation.definitions import _qrule
        rule = _qrule("alt_baro_positive", "Altitude cannot be negative",
                      rule="alt_baro_ft >= 0", dimension="validity")
        assert rule["type"] == "custom"
        assert rule["engine"] == "dqx"
        assert rule["implementation"] == sql_expression_implementation(
            "alt_baro_ft >= 0", "Altitude cannot be negative",
            name="alt_baro_positive", criticality="error",
        )

    def test_sql_expression_implementation_omits_msg_when_none(self):
        impl = sql_expression_implementation("a > 0", None, name="n", criticality="error")
        assert impl["check"]["arguments"] == {"expression": "a > 0"}  # no msg: null
        with_msg = sql_expression_implementation("a > 0", "boom", name="n", criticality="error")
        assert with_msg["check"]["arguments"] == {"expression": "a > 0", "msg": "boom"}


class TestBuildImplementation:
    def test_typed_check_shape(self):
        impl = build_implementation(
            "is_in_list",
            {"column": "position_source", "allowed": ["ADSB", "MLAT"]},
            name="position_source_in_list",
            criticality="error",
        )
        assert impl == {
            "check": {
                "function": "is_in_list",
                "arguments": {"column": "position_source", "allowed": ["ADSB", "MLAT"]},
            },
            "name": "position_source_in_list",
            "criticality": "error",
        }

    def test_arguments_are_copied_not_aliased(self):
        args = {"expression": "x > 0"}
        impl = build_implementation("sql_expression", args, name="n", criticality="error")
        args["expression"] = "MUTATED"
        assert impl["check"]["arguments"]["expression"] == "x > 0"


class TestCatalog:
    def test_excludes_all_constraint_derived_functions(self):
        offered = {c.function for c in CHECK_CATALOG}
        assert offered.isdisjoint(CONSTRAINT_DERIVED_FUNCTIONS), (
            "constraint-equivalent checks must not appear in the explicit picker"
        )

    def test_v1_subset(self):
        v1 = {c.function for c in catalog(v1_only=True)}
        assert {
            "is_in_list", "is_data_fresh", "is_aggr_not_greater_than",
            "foreign_key", "sql_expression",
        } <= v1

    def test_grain_filter_keeps_sql_expression_everywhere(self):
        for grain in ("column", "object"):
            fns = {c.function for c in catalog(grain=grain)}
            assert "sql_expression" in fns
        col = catalog(grain="column")
        assert all(c.grain == "column" or c.function == "sql_expression" for c in col)

    def test_every_check_has_args_and_a_label(self):
        for c in CHECK_CATALOG:
            assert c.label and c.description and c.args
            assert c.grain in ("column", "object")


class TestDisplay:
    def test_sql_expression(self):
        assert to_display({"function": "sql_expression", "arguments": {"expression": "a > b"}}) == "a > b"

    def test_in_list(self):
        assert to_display({"function": "is_in_list", "arguments": {"column": "s", "allowed": ["A"]}}) == "s in ['A']"

    def test_data_fresh(self):
        out = to_display({"function": "is_data_fresh", "arguments": {"column": "ts", "max_age_minutes": 60}})
        assert "fresh within 60" in out

    def test_unique(self):
        out = to_display({"function": "is_unique", "arguments": {"columns": ["a", "b"]}})
        assert out == "unique(a, b)"


class TestSerialize:
    def test_shape_is_json_safe_and_complete(self):
        import json
        data = serialize_catalog()
        json.dumps(data)  # must be JSON-serializable (no dataclasses/sets leak through)
        assert set(data.keys()) == {"checks", "constraint_derived_functions"}
        assert len(data["checks"]) == len(CHECK_CATALOG)
        # constraint_derived is a sorted list (JSON has no sets)
        assert data["constraint_derived_functions"] == sorted(CONSTRAINT_DERIVED_FUNCTIONS)

    def test_each_check_carries_picker_metadata(self):
        for c in serialize_catalog()["checks"]:
            assert {"function", "label", "description", "grain", "args"} <= set(c)
            for a in c["args"]:
                assert {"name", "type", "required"} <= set(a)

    def test_no_constraint_derived_in_serialized_checks(self):
        data = serialize_catalog()
        fns = {c["function"] for c in data["checks"]}
        assert fns.isdisjoint(set(data["constraint_derived_functions"]))


class TestCheckToSqlPredicate:
    def test_sql_expression_passthrough(self):
        assert check_to_sql_predicate("sql_expression", {"expression": "a > b"}) == "a > b"

    def test_in_list_quotes_and_allows_null(self):
        p = check_to_sql_predicate("is_in_list", {"column": "s", "allowed": ["A", "O'B"]})
        assert "`s` IN ('A', 'O''B')" in p and "`s` IS NULL" in p  # escaped + null-tolerant

    def test_not_in_list(self):
        p = check_to_sql_predicate("is_not_in_list", {"column": "s", "forbidden": ["X"]})
        assert "NOT IN ('X')" in p

    def test_data_fresh(self):
        assert "INTERVAL 60 MINUTES" in check_to_sql_predicate("is_data_fresh", {"column": "ts", "max_age_minutes": 60})

    def test_not_in_future(self):
        assert "current_timestamp()" in check_to_sql_predicate("is_not_in_future", {"column": "ts"})

    def test_column_name_is_backtick_quoted(self):
        """Reserved-word/space-containing column names must not break the query."""
        p = check_to_sql_predicate("is_not_in_future", {"column": "order"})
        assert "`order`" in p and "(order " not in p

    def test_column_name_injection_is_neutralized(self):
        """A crafted `column` value must not escape the backtick-quoted identifier."""
        malicious = "x`); DROP TABLE t; --"
        p = check_to_sql_predicate("is_not_in_future", {"column": malicious})
        # The embedded backtick must be escaped (doubled), not left able to close the identifier.
        assert "``" in p
        assert "DROP TABLE t; --`" in p  # neutralized inside the quoted identifier, not executable SQL

    def test_dataset_level_returns_none(self):
        for fn in ("is_unique", "foreign_key", "is_aggr_not_greater_than", "has_no_aggr_outliers"):
            assert check_to_sql_predicate(fn, {"columns": ["a"]}) is None

    def test_not_confidently_translatable_returns_none(self):
        assert check_to_sql_predicate("is_valid_email", {"column": "e"}) is None
        assert check_to_sql_predicate("is_geo_within", {"column": "g"}) is None

    def test_empty_list_returns_none(self):
        assert check_to_sql_predicate("is_in_list", {"column": "s", "allowed": []}) is None

    def test_string_literals_escaped_against_injection(self):
        p = check_to_sql_predicate("is_in_list", {"column": "s", "allowed": ["x'; DROP TABLE t; --"]})
        assert "x''; DROP TABLE t; --" in p  # single quotes doubled
