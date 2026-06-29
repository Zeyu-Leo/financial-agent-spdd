"""Thin async HTTP transport for provider calls.

Owns the single ``httpx.AsyncClient`` per ``LLMService`` instance (one
client, not one-per-call — see Week 1 pitfalls). Tests inject an
``httpx.MockTransport`` so no monkey-patching of the network stack is
needed. This layer knows nothing about providers, retries, or response
shapes — that is ``LLMService``'s job.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

DEFAULT_TIMEOUT = 60.0


class LLMHTTPClient:
    """Async wrapper around a single pooled ``httpx.AsyncClient``."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            transport=transport,
            timeout=timeout,
        )

    async def post_json(self, url: str, payload: dict[str, Any]) -> httpx.Response:
        """POST a JSON body and return the raw response (no error raising).

        Retry and status interpretation belong to ``LLMService``; this
        method only performs the transport.
        """
        return await self._client.post(url, json=payload)

    async def get(self, url: str, *, timeout: float | None = None) -> httpx.Response:
        """GET a URL, optionally overriding the client's default timeout.

        Used by the readiness probe, which wants a short timeout rather
        than the long completion timeout.
        """
        if timeout is None:
            return await self._client.get(url)
        return await self._client.get(url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> LLMHTTPClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
