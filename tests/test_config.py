"""配置加载测试。"""
import pytest

from src.config import load_config, load_deployment_config


def test_load_config_reads_optional_numeric_values(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_TIMEOUT", "30")
    monkeypatch.setenv("DEEPSEEK_MAX_RETRIES", "3")
    config = load_config()
    assert config.timeout == 30
    assert config.max_retries == 3


def test_load_config_rejects_invalid_timeout(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_TIMEOUT", "fast")
    with pytest.raises(RuntimeError, match="必须是整数"):
        load_config()


def test_load_deployment_config_reads_public_limits(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEPLOYMENT", "true")
    monkeypatch.setenv("PUBLIC_SESSION_ACTION_LIMIT", "4")
    monkeypatch.setenv("PUBLIC_DAILY_LLM_CALL_LIMIT", "80")
    config = load_deployment_config()
    assert config.public is True
    assert config.session_action_limit == 4
    assert config.daily_llm_call_limit == 80


def test_load_deployment_config_rejects_invalid_boolean(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEPLOYMENT", "sometimes")
    with pytest.raises(RuntimeError, match="必须是"):
        load_deployment_config()
