"""Phase 4: the agentic generator emits EXECUTABLE DQX checks, not inert text.

The LLM is instructed to emit each quality rule with a `check` (function + arguments)
from the DQX catalog; `_compile_quality_rules` wraps it into the executable
implementation envelope (type=custom, engine=dqx, implementation) so generated rules
actually run. These tests exercise the deterministic compile + prompt wiring (no LLM).
"""
import os
os.environ['TESTING'] = 'true'
os.environ['SKIP_STARTUP_TASKS'] = 'true'

import json

from src.controller.contract_generator_manager import (
    _finalize_contract,
    _compile_quality_rules,
    SYSTEM_PROMPT,
)


class TestPromptVocab:
    def test_prompt_has_dqx_vocab_injected(self):
        assert "__DQX_VOCAB__" not in SYSTEM_PROMPT          # sentinel replaced
        assert "is_in_list" in SYSTEM_PROMPT                 # catalog functions present
        assert "sql_expression" in SYSTEM_PROMPT
        assert "[common]" in SYSTEM_PROMPT                   # v1-subset markers present
        # constraints-first guidance
        assert "DQX generates those checks automatically" in SYSTEM_PROMPT


class TestCompile:
    def test_check_compiled_to_executable_implementation(self):
        contract = {"qualityRules": [{
            "name": "src_in_list", "dimension": "validity", "severity": "error",
            "check": {"function": "is_in_list", "arguments": {"column": "position_source", "allowed": ["ADSB", "MLAT"]}},
        }]}
        warnings = []
        _compile_quality_rules(contract, warnings)
        r = contract["qualityRules"][0]
        assert r["type"] == "custom" and r["engine"] == "dqx"
        assert "check" not in r  # transient field consumed
        impl = json.loads(r["implementation"])
        assert impl["check"]["function"] == "is_in_list"
        assert impl["check"]["arguments"]["allowed"] == ["ADSB", "MLAT"]
        assert impl["criticality"] == "error"
        assert r["rule"]  # derived readable text
        assert warnings == []

    def test_warning_severity_maps_to_warn(self):
        contract = {"qualityRules": [{
            "name": "freshness", "severity": "warning",
            "check": {"function": "is_data_fresh", "arguments": {"column": "ts", "max_age_minutes": 60}},
        }]}
        _compile_quality_rules(contract, [])
        assert json.loads(contract["qualityRules"][0]["implementation"])["criticality"] == "warn"

    def test_sql_expression_check(self):
        contract = {"qualityRules": [{
            "name": "arr_after_dep", "severity": "error",
            "check": {"function": "sql_expression", "arguments": {"expression": "arr_utc > dep_utc"}},
        }]}
        _compile_quality_rules(contract, [])
        impl = json.loads(contract["qualityRules"][0]["implementation"])
        assert impl["check"]["arguments"]["expression"] == "arr_utc > dep_utc"

    def test_unknown_function_left_uncompiled_with_warning(self):
        contract = {"qualityRules": [{
            "name": "bad", "severity": "warning",
            "check": {"function": "not_a_real_check", "arguments": {}},
        }]}
        warnings = []
        _compile_quality_rules(contract, warnings)
        r = contract["qualityRules"][0]
        assert "implementation" not in r          # not compiled
        assert r.get("check")                     # left in place
        assert any("unknown DQX function" in w for w in warnings)

    def test_rule_without_check_is_flagged(self):
        contract = {"qualityRules": [{"name": "inert", "severity": "warning"}]}
        warnings = []
        _compile_quality_rules(contract, warnings)
        assert any("no executable check" in w for w in warnings)


class TestFinalizeRunsCompile:
    def test_finalize_compiles_checks(self):
        contract = {"name": "t", "qualityRules": [{
            "name": "x", "severity": "error",
            "check": {"function": "is_in_list", "arguments": {"column": "c", "allowed": ["a"]}},
        }]}
        out = _finalize_contract(contract, catalog="cat", schema="sch", table="tbl", warnings=[])
        impl = json.loads(out["qualityRules"][0]["implementation"])
        assert impl["check"]["function"] == "is_in_list"
        assert out["qualityRules"][0]["engine"] == "dqx"
