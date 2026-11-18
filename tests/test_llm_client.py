"""LLM客户端测试：响应结构、重试与用户可读异常。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APITimeoutError

from src.config import Config
from src.llm_client import LLMClient, LLMError
from src.usage_limit import PUBLIC_DAILY_LIMITER


def _response(content: str | None, choices: bool = True):
    if not choices:
        return SimpleNamespace(choices=[])
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@patch("src.llm_client.OpenAI")
def test_chat_success(mock_openai):
    mock_openai.return_value.chat.completions.create.return_value = _response('{"ok": true}')
    client = LLMClient(Config(api_key="test", max_retries=0))
    assert client.chat("system", "user") == '{"ok": true}'


@patch("src.llm_client.time.sleep")
@patch("src.llm_client.OpenAI")
def test_timeout_is_retried_then_succeeds(mock_openai, mock_sleep):
    timeout = APITimeoutError(request=httpx.Request("POST", "https://example.com"))
    create = mock_openai.return_value.chat.completions.create
    create.side_effect = [timeout, _response("ok")]
    client = LLMClient(Config(api_key="test", max_retries=1))
    assert client.chat("system", "user", json_mode=False) == "ok"
    assert create.call_count == 2
    mock_sleep.assert_called_once()


@patch("src.llm_client.OpenAI")
def test_empty_choices_has_friendly_error(mock_openai):
    mock_openai.return_value.chat.completions.create.return_value = _response(None, choices=False)
    client = LLMClient(Config(api_key="test", max_retries=0))
    with pytest.raises(LLMError, match="结构异常"):
        client.chat("system", "user")


@patch("src.llm_client.OpenAI", side_effect=ValueError("invalid URL"))
def test_client_initialization_error_is_friendly(mock_openai):
    with pytest.raises(LLMError, match="初始化失败"):
        LLMClient(Config(api_key="test", base_url="not-a-url"))


@patch("src.llm_client.OpenAI")
def test_public_daily_quota_blocks_extra_model_calls(mock_openai):
    PUBLIC_DAILY_LIMITER.reset_for_test()
    mock_openai.return_value.chat.completions.create.return_value = _response("ok")
    client = LLMClient(
        Config(
            api_key="test",
            max_retries=0,
            public_deployment=True,
            daily_llm_call_limit=1,
        )
    )
    assert client.chat("system", "user", json_mode=False) == "ok"
    with pytest.raises(LLMError, match="额度已用完"):
        client.chat("system", "user", json_mode=False)
    PUBLIC_DAILY_LIMITER.reset_for_test()
