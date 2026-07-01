"""FastAPI application entrypoint.

Builds the ServicesContainer in the lifespan, installs request-id
middleware that binds ``X-Request-Id`` (or a fresh UUIDv4) into the
logging ContextVar and echoes it on the response.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.core.exceptions import LLMProviderError
from app.core.logging import (
    bind_request_id,
    configure_logging,
    get_request_id,
    reset_request_id,
)
from app.core.services_container import ServicesContainer
from app.services.llm_client import LLMHTTPClient
from app.services.llm_service import LLMService

REQUEST_ID_HEADER = "X-Request-Id"


def _build_http_client(settings: Settings) -> LLMHTTPClient:
    if settings.llm_provider == "openrouter":
        return LLMHTTPClient(
            settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
        )
    if settings.llm_provider == "portkey":
        headers: dict[str, str] = {}
        if settings.portkey_api_key:
            headers["x-portkey-api-key"] = settings.portkey_api_key
        if settings.portkey_provider:
            headers["x-portkey-provider"] = settings.portkey_provider
        return LLMHTTPClient(
            settings.portkey_base_url,
            api_key=settings.portkey_provider_api_key,  # forwarded as Authorization
            extra_headers=headers,
        )
    return LLMHTTPClient(settings.ollama_base_url)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_format)
    http_client = _build_http_client(settings)
    container = ServicesContainer(
        settings=settings,
        llm_service=LLMService(settings, http_client),
    )
    app.state.container = container
    try:
        yield
    finally:
        await http_client.aclose()


app = FastAPI(title="Financial Helpdesk Agent", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    token = bind_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        reset_request_id(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> Response:
    """Readiness: probe the configured LLM provider once.

    Returns 503 (not 200) when the provider is unreachable so an
    orchestrator does not route traffic to an app that cannot serve.
    The Postgres readiness check is added with Task 2.
    """
    container: ServicesContainer = app.state.container
    try:
        await container.llm_service.check_liveness()
    except LLMProviderError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error_code": "provider_unavailable",
                "message": str(exc),
                "request_id": get_request_id(),
            },
        )
    return JSONResponse(
        status_code=200,
        content={"status": "ready", "provider": container.settings.llm_provider},
    )
