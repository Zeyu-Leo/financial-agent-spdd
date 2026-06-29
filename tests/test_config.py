"""Config validation acceptance (Task 1 criteria 1-2)."""

import pytest

from app.core.config import Settings, get_settings


def _settings(**env: str) -> Settings:
    # Construct directly from explicit values, bypassing .env / cache so
    # each test is isolated.
    return Settings(**env)  # type: ignore[arg-type]


def test_openrouter_model_default_prints() -> None:
    s = _settings(pg_dsn="postgresql://x", llm_provider="ollama")
    assert s.openrouter_model == "gpt-4.1-mini"


def test_openrouter_requires_api_key() -> None:
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        _settings(pg_dsn="postgresql://x", llm_provider="openrouter")


def test_ollama_does_not_require_openrouter_key() -> None:
    s = _settings(pg_dsn="postgresql://x", llm_provider="ollama")
    assert s.openrouter_api_key is None


def test_openrouter_with_key_validates() -> None:
    s = _settings(
        pg_dsn="postgresql://x",
        llm_provider="openrouter",
        openrouter_api_key="sk-test",
    )
    assert s.llm_provider == "openrouter"


def test_get_settings_is_cached() -> None:
    assert get_settings.cache_info  # lru_cache wrapped
