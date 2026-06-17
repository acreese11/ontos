"""Ask-Ontos copilot records contract-draft turns into llm_sessions like chat turns.

`_summarize_draft_turn` builds the assistant message persisted after a draft stream
drains, so the recorded history reads like a chat turn (headline + link on success,
the existing-contract message, or a failure note). These pin each terminal branch.
"""
import os
os.environ['TESTING'] = 'true'
os.environ['SKIP_STARTUP_TASKS'] = 'true'

from src.routes.contract_generator_routes import _summarize_draft_turn

CAT, SCH, TBL = "safe_skies", "flight_ops", "adsb_v2"
FQN = "safe_skies.flight_ops.adsb_v2"


class TestSummarizeDraftTurn:
    def test_no_terminal_event(self):
        assert _summarize_draft_turn(CAT, SCH, TBL, None) == f"Drafted a data contract for `{FQN}`."

    def test_result_with_name_version_and_link(self):
        terminal = {
            "type": "result",
            "contract": {"name": "live_flights", "version": "1.0.0"},
            "contract_id": "abc-123",
        }
        out = _summarize_draft_turn(CAT, SCH, TBL, terminal)
        assert "Drafted `live_flights` v1.0.0." in out
        assert "/data-contracts/abc-123?ai-draft=true" in out

    def test_result_without_contract_id_has_no_link(self):
        terminal = {"type": "result", "contract": {"name": "live_flights"}}
        out = _summarize_draft_turn(CAT, SCH, TBL, terminal)
        assert "Drafted `live_flights`." in out
        assert "/data-contracts/" not in out

    def test_result_missing_name_falls_back_to_fqn(self):
        terminal = {"type": "result", "contract": {}, "contract_id": "x"}
        out = _summarize_draft_turn(CAT, SCH, TBL, terminal)
        assert f"a data contract for `{FQN}`" in out
        assert "/data-contracts/x?ai-draft=true" in out

    def test_exists_uses_message(self):
        terminal = {"type": "exists", "message": "A contract for adsb_v2 already exists."}
        assert _summarize_draft_turn(CAT, SCH, TBL, terminal) == "A contract for adsb_v2 already exists."

    def test_exists_without_message_falls_back(self):
        out = _summarize_draft_turn(CAT, SCH, TBL, {"type": "exists"})
        assert out == f"A contract for `{FQN}` already exists."

    def test_error_includes_message(self):
        out = _summarize_draft_turn(CAT, SCH, TBL, {"type": "error", "message": "boom"})
        assert "⚠️" in out and "boom" in out and FQN in out

    def test_unknown_type_falls_back(self):
        out = _summarize_draft_turn(CAT, SCH, TBL, {"type": "weird"})
        assert out == f"Drafted a data contract for `{FQN}`."
