"""Config validation acceptance (Task 1 criteria 1-2)."""

import pytest

from app.core.config import Settings, get_settings


def _settings(**env: str) -> Settings:
    # Isolate validation tests from the developer's .env file (which may set a
    # real provider/key); `_env_file=None` disables file loading. OS env vars
    # are still read by pydantic-settings — negative tests clear those too.
    return Settings(_env_file=None, **env)  # type: ignore[arg-type]


def test_openrouter_model_default_prints() -> None:
    s = _settings(pg_dsn="postgresql://x", chat_provider="ollama")
    assert s.openrouter_model == "gpt-4.1-mini"


def test_openrouter_requires_api_key() -> None:
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        _settings(pg_dsn="postgresql://x", chat_provider="openrouter")


def test_ollama_does_not_require_openrouter_key() -> None:
    s = _settings(pg_dsn="postgresql://x", chat_provider="ollama")
    assert s.openrouter_api_key is None


def test_openrouter_with_key_validates() -> None:
    s = _settings(
        pg_dsn="postgresql://x",
        chat_provider="openrouter",
        openrouter_api_key="sk-test",
    )
    assert s.chat_provider == "openrouter"


def _clear_portkey_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # pydantic-settings reads OS env vars; a stray PORTKEY_* in the shell
    # (the dev's own Portkey routing) would otherwise mask these negatives.
    monkeypatch.delenv("PORTKEY_API_KEY", raising=False)
    monkeypatch.delenv("PORTKEY_PROVIDER", raising=False)


def test_portkey_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_portkey_env(monkeypatch)
    with pytest.raises(ValueError, match="PORTKEY_API_KEY"):
        _settings(pg_dsn="postgresql://x", chat_provider="portkey", portkey_provider="openai")


def test_portkey_requires_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_portkey_env(monkeypatch)
    with pytest.raises(ValueError, match="PORTKEY_PROVIDER"):
        _settings(pg_dsn="postgresql://x", chat_provider="portkey", portkey_api_key="pk-test")


def test_portkey_with_keys_validates() -> None:
    s = _settings(
        pg_dsn="postgresql://x",
        chat_provider="portkey",
        portkey_api_key="pk-test",
        portkey_provider="openai",
    )
    assert s.chat_provider == "portkey"


def test_get_settings_is_cached() -> None:
    assert get_settings.cache_info  # lru_cache wrapped
