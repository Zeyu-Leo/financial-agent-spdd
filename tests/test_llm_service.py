"""LLMService acceptance: provider endpoints, unwrapping, bounded retries,
embed batch + dimension check (Task 1 criteria 3-5 + embed criteria)."""

import json
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import LLMProviderError
from app.core.logging import configure_logging
from app.services import llm_service as llm_service_mod
from app.services.llm_client import LLMHTTPClient
from app.services.llm_service import LLMService


def _json_records(out: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in out.strip().splitlines() if line.strip().startswith("{")]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep retry tests fast: collapse backoff to a no-op."""

    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(llm_service_mod.asyncio, "sleep", _instant)


def _service(provider: str, handler: httpx.MockTransport, *, embedding_dim: int = 3) -> LLMService:
    settings = Settings(  # type: ignore[call-arg]
        pg_dsn="postgresql://x",
        llm_provider=provider,
        openrouter_api_key="sk-test" if provider == "openrouter" else None,
        embedding_dim=embedding_dim,
    )
    base = settings.openrouter_base_url if provider == "openrouter" else settings.ollama_base_url
    client = LLMHTTPClient(base, transport=handler)
    return LLMService(settings, client)


# --------------------------------------------------------------------- #
# complete()
# --------------------------------------------------------------------- #
async def test_openrouter_complete_endpoint() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi there"}}]})

    svc = _service("openrouter", httpx.MockTransport(handler))
    out = await svc.complete(messages=[{"role": "user", "content": "hi"}])
    assert out == "hi there"
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"


async def test_ollama_complete_endpoint_and_unwrap() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"message": {"content": "local answer"}})

    svc = _service("ollama", httpx.MockTransport(handler))
    out = await svc.complete(messages=[{"role": "user", "content": "hi"}])
    assert out == "local answer"
    assert seen["url"] == "http://localhost:11434/api/chat"


# --------------------------------------------------------------------- #
# retries
# --------------------------------------------------------------------- #
async def test_retries_three_times_then_raises() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"error": "overloaded"})

    svc = _service("ollama", httpx.MockTransport(handler))
    with pytest.raises(LLMProviderError) as exc:
        await svc.complete(messages=[{"role": "user", "content": "hi"}])
    assert calls["n"] == 3
    assert exc.value.status_code == 503


async def test_client_error_does_not_retry() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    svc = _service("ollama", httpx.MockTransport(handler))
    with pytest.raises(LLMProviderError):
        await svc.complete(messages=[{"role": "user", "content": "hi"}])
    assert calls["n"] == 1


async def test_timeout_is_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.TimeoutException("slow", request=request)

    svc = _service("ollama", httpx.MockTransport(handler))
    with pytest.raises(LLMProviderError):
        await svc.complete(messages=[{"role": "user", "content": "hi"}])
    assert calls["n"] == 3


# --------------------------------------------------------------------- #
# embed()
# --------------------------------------------------------------------- #
async def test_openrouter_embed_endpoint_and_order() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        # Deliberately out of order; service must sort by index.
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.4, 0.5, 0.6]},
                    {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                ]
            },
        )

    svc = _service("openrouter", httpx.MockTransport(handler))
    out = await svc.embed(inputs=["a", "b"])
    assert seen["url"] == "https://openrouter.ai/api/v1/embeddings"
    assert out == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


async def test_ollama_embed_endpoint() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]})

    svc = _service("ollama", httpx.MockTransport(handler))
    out = await svc.embed(inputs=["a", "b"])
    assert seen["url"] == "http://localhost:11434/api/embed"
    assert '"input"' in seen["body"]
    assert len(out) == 2


async def test_embed_dimension_mismatch_raises() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})  # dim 2

    svc = _service("ollama", httpx.MockTransport(handler), embedding_dim=768)
    with pytest.raises(LLMProviderError, match="dim"):
        await svc.embed(inputs=["a"])


async def test_malformed_completion_shape_raises() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    svc = _service("ollama", httpx.MockTransport(handler))
    with pytest.raises(LLMProviderError):
        await svc.complete(messages=[{"role": "user", "content": "hi"}])


# --------------------------------------------------------------------- #
# check_liveness() — readiness probe
# --------------------------------------------------------------------- #
async def test_liveness_ollama_probes_tags() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"models": []})

    svc = _service("ollama", httpx.MockTransport(handler))
    await svc.check_liveness()  # no raise
    assert seen["url"] == "http://localhost:11434/api/tags"


async def test_liveness_openrouter_probes_models() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": []})

    svc = _service("openrouter", httpx.MockTransport(handler))
    await svc.check_liveness()
    assert seen["url"] == "https://openrouter.ai/api/v1/models"


async def test_liveness_raises_when_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    svc = _service("ollama", httpx.MockTransport(handler))
    with pytest.raises(LLMProviderError):
        await svc.check_liveness()


# --------------------------------------------------------------------- #
# observability: duration_ms on success, error event on terminal failure
# --------------------------------------------------------------------- #
async def test_complete_success_logs_duration_ms(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "ok"}})

    svc = _service("ollama", httpx.MockTransport(handler))
    configure_logging("json")
    await svc.complete(messages=[{"role": "user", "content": "hi"}])

    records = _json_records(capsys.readouterr().out)
    done = [r for r in records if r.get("event") == "llm.complete"]
    assert done, "expected an llm.complete success record"
    assert isinstance(done[0]["duration_ms"], int)


async def test_complete_terminal_failure_logs_error_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "overloaded"})

    svc = _service("ollama", httpx.MockTransport(handler))
    configure_logging("json")
    with pytest.raises(LLMProviderError):
        await svc.complete(messages=[{"role": "user", "content": "hi"}])

    records = _json_records(capsys.readouterr().out)
    failed = [r for r in records if r.get("event") == "llm.complete.failed"]
    assert failed, "expected an llm.complete.failed error record"
    assert failed[0]["level"] == "ERROR"
    assert "duration_ms" in failed[0]


async def test_liveness_does_not_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("down", request=request)

    svc = _service("ollama", httpx.MockTransport(handler))
    with pytest.raises(LLMProviderError):
        await svc.check_liveness()
    assert calls["n"] == 1  # single probe, no 3-attempt retry
