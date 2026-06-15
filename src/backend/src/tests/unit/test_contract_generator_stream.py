"""Unit tests for ContractGeneratorManager.generate_stream event protocol.

Mocks the UC/warehouse/LLM I/O (module-level helpers + stream_chat_completion)
and asserts the streamed event sequence the Ask Ontos panel depends on.
"""
from unittest.mock import MagicMock

import pytest

import src.controller.contract_generator_manager as m
from src.controller.contract_generator_manager import ContractGeneratorManager


def _make_manager(contracts_manager=None):
    settings = MagicMock()
    settings.LLM_ENDPOINT = "databricks-claude-opus-4-7"
    settings.DATABRICKS_WAREHOUSE_ID = "wh123"
    ws = MagicMock()
    ws.tables.get.return_value = MagicMock(comment="")
    ws.config.authenticate.return_value = {"Authorization": "Bearer tok"}
    return ContractGeneratorManager(settings, contracts_manager=contracts_manager, workspace_client=ws)


@pytest.fixture
def patched_io(monkeypatch):
    monkeypatch.setattr(m, "_inspect_columns", lambda ws, c, s, t: [{"name": "id", "type_name": "LONG", "nullable": False, "comment": ""}])
    monkeypatch.setattr(m, "_sample_rows", lambda ws, wid, c, s, t, n=20: [{"id": 1}])
    monkeypatch.setattr(m, "_column_stats", lambda ws, wid, c, s, t, cols: {"id": {"nulls": 0}})
    monkeypatch.setattr(m, "_build_user_prompt", lambda *a, **k: "PROMPT")
    monkeypatch.setattr(m, "create_openai_client", lambda settings, user_token=None: MagicMock())
    monkeypatch.setattr(m, "stream_chat_completion", lambda client, **kw: iter(['{"name":', ' "x"}']))
    monkeypatch.setattr(m, "_extract_json", lambda content: {"name": "x", "schema": []})
    return monkeypatch


def test_event_sequence_and_token_placement(patched_io):
    mgr = _make_manager()
    events = list(mgr.generate_stream(catalog="c", schema="s", table="t", db=None))

    # Stage 'done' events arrive in pipeline order.
    done = [e["step"] for e in events if e["type"] == "stage" and e["status"] == "done"]
    assert done == ["inspect_columns", "sample_rows", "column_stats", "llm_call", "parse_validate"]

    # Tokens are emitted verbatim, and strictly between llm_call start and done.
    tokens = [e["delta"] for e in events if e["type"] == "token"]
    assert tokens == ['{"name":', ' "x"}']
    i_start = next(i for i, e in enumerate(events) if e["type"] == "stage" and e["step"] == "llm_call" and e["status"] == "start")
    i_done = next(i for i, e in enumerate(events) if e["type"] == "stage" and e["step"] == "llm_call" and e["status"] == "done")
    assert all(i_start < i < i_done for i, e in enumerate(events) if e["type"] == "token")

    # Terminal result; no persistence when db is None.
    assert events[-1]["type"] == "result"
    assert events[-1]["contract_id"] is None
    assert events[-1]["contract"]["name"] == "x"
    # AI-draft markers applied via the shared finalize helper.
    cps = events[-1]["contract"]["customProperties"]
    assert any(cp["property"] == "generatedBy" for cp in cps)


def test_persists_and_returns_id_with_force(patched_io):
    cm = MagicMock()
    cm.create_contract_with_relations.return_value = MagicMock(id="cid-1")
    mgr = _make_manager(contracts_manager=cm)
    events = list(mgr.generate_stream(catalog="c", schema="s", table="t", db=MagicMock(), current_user="me", force=True))
    assert events[-1]["type"] == "result"
    assert events[-1]["contract_id"] == "cid-1"
    cm.create_contract_with_relations.assert_called_once()


def test_exists_short_circuit_skips_llm(patched_io, monkeypatch):
    cm = MagicMock()
    mgr = _make_manager(contracts_manager=cm)
    monkeypatch.setattr(
        ContractGeneratorManager,
        "find_existing_for_table",
        staticmethod(lambda db, c, s, t: [{"contract_id": "old", "name": "n", "status": "draft"}]),
    )
    events = list(mgr.generate_stream(catalog="c", schema="s", table="t", db=MagicMock(), force=False))
    assert len(events) == 1 and events[0]["type"] == "exists"
    cm.create_contract_with_relations.assert_not_called()


def test_persist_failure_still_yields_contract(patched_io):
    cm = MagicMock()
    cm.create_contract_with_relations.side_effect = RuntimeError("db down")
    mgr = _make_manager(contracts_manager=cm)
    events = list(mgr.generate_stream(catalog="c", schema="s", table="t", db=MagicMock(), force=True))
    result = events[-1]
    assert result["type"] == "result"
    assert result["contract_id"] is None
    assert result["contract"]["name"] == "x"
    assert any("save failed" in w for w in result["warnings"])
