"""Tests for the shared LLM client factory."""
from unittest.mock import MagicMock, patch

import pytest

from src.common.llm_client import create_openai_client, chat_completion


def _make_settings(**overrides):
    s = MagicMock()
    s.DATABRICKS_TOKEN = overrides.get("token", "dapi-test")
    s.DATABRICKS_HOST = overrides.get("host", "https://test.databricks.com")
    s.LLM_BASE_URL = overrides.get("base_url", "")
    return s


class TestCreateOpenaiClient:
    @patch("src.common.llm_client.OpenAI")
    def test_uses_user_token_when_provided(self, mock_openai_cls):
        settings = _make_settings(token="should-not-be-used")
        create_openai_client(settings, user_token="obo-token")

        mock_openai_cls.assert_called_once()
        assert mock_openai_cls.call_args[1]["api_key"] == "obo-token"

    @patch("src.common.llm_client.OpenAI")
    def test_falls_back_to_settings_token(self, mock_openai_cls):
        settings = _make_settings(token="pat-token")
        create_openai_client(settings)

        assert mock_openai_cls.call_args[1]["api_key"] == "pat-token"

    @patch("src.common.llm_client.OpenAI")
    def test_derives_base_url_from_host(self, mock_openai_cls):
        settings = _make_settings(base_url="")
        create_openai_client(settings)

        assert mock_openai_cls.call_args[1]["base_url"] == "https://test.databricks.com/serving-endpoints"

    @patch("src.common.llm_client.OpenAI")
    def test_explicit_base_url_wins(self, mock_openai_cls):
        settings = _make_settings(base_url="https://custom.endpoint/v1")
        create_openai_client(settings)

        assert mock_openai_cls.call_args[1]["base_url"] == "https://custom.endpoint/v1"

    @patch.dict("os.environ", {}, clear=True)
    def test_raises_when_no_token(self):
        settings = _make_settings(token=None)
        settings.DATABRICKS_TOKEN = None

        with pytest.raises(RuntimeError, match="No authentication token"):
            create_openai_client(settings)

    @patch("src.common.llm_client.OpenAI")
    def test_raises_when_no_base_url(self, mock_openai_cls):
        settings = _make_settings(base_url="")
        settings.DATABRICKS_HOST = ""

        with pytest.raises(RuntimeError, match="LLM_BASE_URL"):
            create_openai_client(settings)


_TEMP_400 = (
    "Error code: 400 - BAD_REQUEST: Model us.anthropic.claude-opus-4-7 "
    "does not support the temperature parameter."
)


def _client(create_fn):
    """Build a fake OpenAI client whose chat.completions.create == create_fn."""
    client = MagicMock()
    client.chat.completions.create.side_effect = create_fn
    return client


class TestChatCompletion:
    def test_retries_without_temperature_on_unsupported(self):
        calls = []

        def create(**kwargs):
            calls.append(dict(kwargs))
            if "temperature" in kwargs:
                raise Exception(_TEMP_400)
            return {"ok": True}

        out = chat_completion(_client(create), model="x", messages=[], temperature=0.2)
        assert out == {"ok": True}
        assert len(calls) == 2
        assert "temperature" not in calls[-1]

    def test_passes_through_when_accepted(self):
        calls = []

        def create(**kwargs):
            calls.append(dict(kwargs))
            return {"ok": True}

        chat_completion(_client(create), model="x", messages=[], temperature=0.2)
        assert len(calls) == 1  # no retry

    def test_unrelated_error_propagates(self):
        def create(**kwargs):
            raise Exception("Error code: 500 - internal")

        with pytest.raises(Exception, match="internal"):
            chat_completion(_client(create), model="x", messages=[], temperature=0.2)

    def test_no_temperature_kwarg_means_no_retry(self):
        # A temperature-rejection error must NOT be swallowed if the caller
        # never sent temperature (would mask a real, different problem).
        def create(**kwargs):
            raise Exception(_TEMP_400)

        with pytest.raises(Exception, match="temperature"):
            chat_completion(_client(create), model="x", messages=[])
