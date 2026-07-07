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
from app.core.db import get_sessionmaker, make_engine
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
from app.services.retrieval_service import RetrievalService

REQUEST_ID_HEADER = "X-Request-Id"


def build_http_client(settings: Settings, provider: str) -> LLMHTTPClient:
    """Construct an HTTP client for ``provider`` from ``Settings``.

    The single place provider selection happens. Called once per capability
    (chat / embedding) and reused by the offline ingest scripts so provider
    branching is never duplicated.
    """
    if provider == "openrouter":
        return LLMHTTPClient(
            settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
        )
    if provider == "portkey":
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


def build_llm_clients(settings: Settings) -> tuple[LLMHTTPClient, LLMHTTPClient]:
    """Build the (chat, embedding) client pair, reusing one when they match."""
    chat_client = build_http_client(settings, settings.chat_provider)
    if settings.embedding_provider == settings.chat_provider:
        return chat_client, chat_client
    return chat_client, build_http_client(settings, settings.embedding_provider)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_format)
    chat_client, embedding_client = build_llm_clients(settings)
    llm_service = LLMService(settings, chat_client, embedding_client)
    engine = make_engine(settings.pg_dsn)
    container = ServicesContainer(
        settings=settings,
        llm_service=llm_service,
        retrieval=RetrievalService(
            get_sessionmaker(engine),
            llm_service,
            embedding_dim=settings.embedding_dim,
        ),
    )
    app.state.container = container
    try:
        yield
    finally:
        await chat_client.aclose()
        if embedding_client is not chat_client:
            await embedding_client.aclose()
        engine.dispose()


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
        content={
            "status": "ready",
            "chat_provider": container.settings.chat_provider,
            "embedding_provider": container.settings.embedding_provider,
        },
    )
