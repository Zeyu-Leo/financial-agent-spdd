"""API wiring: request-id middleware echo + /readyz (Task 1 Operation 6)."""

import pathlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Ollama provider needs no api key; give a pg_dsn so Settings validates.
    monkeypatch.setenv("PG_DSN", "postgresql+psycopg://x")
    monkeypatch.setenv("CHAT_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.api.main import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_readyz_ready_when_provider_reachable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.llm_service import LLMService

    async def _ok(self: LLMService, *, request_id: str | None = None) -> None:
        return None

    monkeypatch.setattr(LLMService, "check_liveness", _ok)
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_readyz_503_when_provider_unreachable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.exceptions import LLMProviderError
    from app.services.llm_service import LLMService

    async def _down(self: LLMService, *, request_id: str | None = None) -> None:
        raise LLMProviderError("unreachable", provider="ollama")

    monkeypatch.setattr(LLMService, "check_liveness", _down)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "provider_unavailable"


def test_request_id_echoed_when_supplied(client: TestClient) -> None:
    resp = client.get("/healthz", headers={"X-Request-Id": "abc-123"})
    assert resp.headers["X-Request-Id"] == "abc-123"


def test_request_id_generated_when_absent(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.headers.get("X-Request-Id")
    # A fresh UUIDv4 contains 4 hyphens.
    assert resp.headers["X-Request-Id"].count("-") == 4


def test_no_os_getenv_outside_config() -> None:
    """Safeguard 1: only config.py reads the environment directly."""
    app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders: list[str] = []
    for path in app_dir.rglob("*.py"):
        if path.name == "config.py":
            continue
        text = path.read_text()
        if "os.getenv" in text or "os.environ" in text:
            offenders.append(str(path))
    assert not offenders, f"env access outside config.py: {offenders}"
