"""Provider-agnostic LLM facade.

Two methods — ``complete`` (chat) and ``embed`` (batch embeddings) —
route by ``Settings.llm_provider``. Provider differences (endpoints,
request shapes, response unwrapping) live entirely inside this class;
callers never see them. Transient failures retry with exponential
backoff up to a fixed 3 attempts (no ``max_retries`` knob), then raise
``LLMProviderError``.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from loguru import logger

from app.core.config import Settings
from app.core.exceptions import LLMProviderError
from app.core.logging import get_request_id, truncate_prompt
from app.services.llm_client import LLMHTTPClient

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.5
# A readiness probe must be fast: single attempt, short timeout, no retry.
LIVENESS_TIMEOUT_SECONDS = 5.0
# 5xx are transient; 4xx are caller/config errors and must not retry.
_TRANSIENT_NETWORK_ERRORS = (httpx.TimeoutException, httpx.RequestError)
# Providers that speak the OpenAI-compatible API (same request/response shape).
# Portkey is a gateway in front of an upstream provider; OpenRouter is direct.
# DeepSeek and Qwen (DashScope) also expose the same /chat/completions endpoint.
_OPENAI_COMPATIBLE = frozenset({"openrouter", "portkey", "deepseek", "qwen"})


def _elapsed_ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


class LLMService:
    def __init__(
        self,
        settings: Settings,
        chat_client: LLMHTTPClient,
        embedding_client: LLMHTTPClient,
    ) -> None:
        self._settings = settings
        # Chat and embedding may target different providers, so each has its
        # own HTTP client (main.py may pass the same object when they match).
        self._chat = chat_client
        self._embed = embedding_client

    def _chat_model(self) -> str:
        """Default chat model for the chat provider."""
        if self._settings.chat_provider == "portkey":
            return self._settings.portkey_model
        if self._settings.chat_provider == "ollama":
            return self._settings.ollama_chat_model
        if self._settings.chat_provider == "deepseek":
            return self._settings.deepseek_model
        if self._settings.chat_provider == "qwen":
            return self._settings.qwen_model
        return self._settings.openrouter_model

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: str | None = None,
        request_id: str | None = None,
    ) -> str:
        provider = self._settings.chat_provider
        rid = request_id or get_request_id()
        if provider in _OPENAI_COMPATIBLE:
            url = "/chat/completions"
            payload: dict[str, Any] = {
                "model": model or self._chat_model(),
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            if response_format is not None:
                payload["response_format"] = {"type": response_format}
        else:
            url = "/api/chat"
            payload = {
                "model": model or self._settings.ollama_chat_model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature},
            }
            if max_tokens is not None:
                payload["options"]["num_predict"] = max_tokens

        prompt_preview, truncated = truncate_prompt(str(messages))
        start = time.perf_counter()
        try:
            data = await self._request_with_retries(url, payload, provider, rid, self._chat)
        except LLMProviderError:
            logger.error(
                "llm.complete.failed",
                event="llm.complete.failed",
                request_id=rid,
                provider=provider,
                url=url,
                duration_ms=_elapsed_ms(start),
            )
            raise
        result = self._unwrap_completion(data, provider, rid)
        logger.info(
            "llm.complete",
            event="llm.complete",
            request_id=rid,
            provider=provider,
            url=url,
            prompt=prompt_preview,
            _truncated=truncated,
            duration_ms=_elapsed_ms(start),
        )
        return result

    async def embed(
        self,
        inputs: list[str],
        *,
        model: str | None = None,
        request_id: str | None = None,
    ) -> list[list[float]]:
        provider = self._settings.embedding_provider
        rid = request_id or get_request_id()
        if provider in _OPENAI_COMPATIBLE:
            url = "/embeddings"
            payload: dict[str, Any] = {
                "model": model or self._settings.embedding_model,
                "input": inputs,
            }
        else:
            url = "/api/embed"
            payload = {
                "model": model or self._settings.embedding_model,
                "input": inputs,
            }

        start = time.perf_counter()
        try:
            data = await self._request_with_retries(url, payload, provider, rid, self._embed)
        except LLMProviderError:
            logger.error(
                "llm.embed.failed",
                event="llm.embed.failed",
                request_id=rid,
                provider=provider,
                url=url,
                n_inputs=len(inputs),
                duration_ms=_elapsed_ms(start),
            )
            raise
        vectors = self._unwrap_embeddings(data, provider, rid)
        self._check_dimensions(vectors, provider, rid)
        logger.info(
            "llm.embed",
            event="llm.embed",
            request_id=rid,
            provider=provider,
            url=url,
            n_inputs=len(inputs),
            duration_ms=_elapsed_ms(start),
        )
        return vectors

    async def check_liveness(self, *, request_id: str | None = None) -> None:
        """Probe every configured provider once; raise if any is unreachable.

        Chat and embedding may target different providers, so both are
        probed (deduplicated when they share a client). Deliberately
        bypasses the 3-attempt retry path: a readiness probe must answer
        fast, not wait out backoff. Used by ``GET /readyz``.
        """
        rid = request_id or get_request_id()
        targets: list[tuple[str, LLMHTTPClient]] = [(self._settings.chat_provider, self._chat)]
        if self._embed is not self._chat:
            targets.append((self._settings.embedding_provider, self._embed))
        for provider, client in targets:
            await self._probe(provider, client, rid)

    async def _probe(self, provider: str, client: LLMHTTPClient, rid: str | None) -> None:
        url = "/api/tags" if provider == "ollama" else "/models"
        try:
            response = await client.get(url, timeout=LIVENESS_TIMEOUT_SECONDS)
        except _TRANSIENT_NETWORK_ERRORS as exc:
            raise LLMProviderError(
                "provider liveness probe failed to connect",
                provider=provider,
                payload={"error": str(exc)},
                request_id=rid,
            ) from exc
        if response.status_code >= 400:
            raise LLMProviderError(
                "provider liveness probe returned an error status",
                provider=provider,
                status_code=response.status_code,
                payload=_response_body(response),
                request_id=rid,
            )

    # ------------------------------------------------------------------ #
    # Transport + retry
    # ------------------------------------------------------------------ #
    async def _request_with_retries(
        self,
        url: str,
        payload: dict[str, Any],
        provider: str,
        request_id: str | None,
        client: LLMHTTPClient,
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await client.post_json(url, payload)
            except _TRANSIENT_NETWORK_ERRORS as exc:
                last_exc = exc
                logger.warning(
                    "llm.retry",
                    event="llm.retry",
                    request_id=request_id,
                    provider=provider,
                    attempt=attempt,
                    reason=type(exc).__name__,
                )
            else:
                if response.status_code >= 500:
                    last_exc = LLMProviderError(
                        "transient provider 5xx",
                        provider=provider,
                        status_code=response.status_code,
                        payload=_response_body(response),
                        request_id=request_id,
                    )
                    logger.warning(
                        "llm.retry",
                        event="llm.retry",
                        request_id=request_id,
                        provider=provider,
                        attempt=attempt,
                        status_code=response.status_code,
                    )
                elif response.status_code >= 400:
                    # Non-transient: caller/config error. Do not retry.
                    raise LLMProviderError(
                        "provider returned a client error",
                        provider=provider,
                        status_code=response.status_code,
                        payload=_response_body(response),
                        request_id=request_id,
                    )
                else:
                    return _response_json(response, provider, request_id)

            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))

        # Exhausted all attempts.
        if isinstance(last_exc, LLMProviderError):
            raise last_exc
        raise LLMProviderError(
            "provider call failed after retries",
            provider=provider,
            status_code=None,
            payload={"error": str(last_exc)},
            request_id=request_id,
        )

    # ------------------------------------------------------------------ #
    # Response unwrapping
    # ------------------------------------------------------------------ #
    def _unwrap_completion(
        self, data: dict[str, Any], provider: str, request_id: str | None
    ) -> str:
        try:
            if provider in _OPENAI_COMPATIBLE:
                content = data["choices"][0]["message"]["content"]
            else:
                content = data["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                "unexpected completion response shape",
                provider=provider,
                payload=data,
                request_id=request_id,
            ) from exc
        if not isinstance(content, str):
            raise LLMProviderError(
                "completion content was not a string",
                provider=provider,
                payload=data,
                request_id=request_id,
            )
        return content

    def _unwrap_embeddings(
        self, data: dict[str, Any], provider: str, request_id: str | None
    ) -> list[list[float]]:
        try:
            if provider in _OPENAI_COMPATIBLE:
                items = sorted(data["data"], key=lambda d: d["index"])
                vectors = [item["embedding"] for item in items]
            else:
                vectors = data["embeddings"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                "unexpected embeddings response shape",
                provider=provider,
                payload=data,
                request_id=request_id,
            ) from exc
        if not isinstance(vectors, list) or not all(isinstance(v, list) for v in vectors):
            raise LLMProviderError(
                "embeddings payload was not a list of vectors",
                provider=provider,
                payload=data,
                request_id=request_id,
            )
        return vectors

    def _check_dimensions(
        self, vectors: list[list[float]], provider: str, request_id: str | None
    ) -> None:
        expected = self._settings.embedding_dim
        for vector in vectors:
            if len(vector) != expected:
                raise LLMProviderError(
                    f"embedding dim {len(vector)} != configured {expected}",
                    provider=provider,
                    payload={"got_dim": len(vector), "expected_dim": expected},
                    request_id=request_id,
                )


def _response_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"text": response.text}


def _response_json(
    response: httpx.Response, provider: str, request_id: str | None
) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise LLMProviderError(
            "provider returned non-JSON body",
            provider=provider,
            status_code=response.status_code,
            payload={"text": response.text},
            request_id=request_id,
        ) from exc
    if not isinstance(body, dict):
        raise LLMProviderError(
            "provider returned a non-object JSON body",
            provider=provider,
            status_code=response.status_code,
            payload=body,
            request_id=request_id,
        )
    return body
