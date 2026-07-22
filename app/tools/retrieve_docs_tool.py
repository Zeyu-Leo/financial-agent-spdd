"""Graph tool: dense retrieval over embedded policy docs."""

from __future__ import annotations

import time

from loguru import logger

from app.core.exceptions import LLMProviderError
from app.core.services_container import ServicesContainer
from app.core.state import AgentState


async def retrieve_docs_tool(state: AgentState, *, services: ServicesContainer) -> AgentState:
    request_id = state.get("request_id")
    user_query = state.get("user_query", "")
    start = time.perf_counter()
    try:
        docs = await services.retrieval.retrieve_docs(
            user_query,
            top_k=5,
            request_id=request_id,
        )
    except LLMProviderError:
        logger.warning(
            "retrieve_docs_failed",
            event="retrieve_docs",
            node_name="retrieve_docs_tool",
            request_id=request_id,
            duration_ms=round((time.perf_counter() - start) * 1000),
        )
        raise

    logger.info(
        "retrieve_docs_done",
        event="retrieve_docs",
        node_name="retrieve_docs_tool",
        request_id=request_id,
        result_count=len(docs),
        duration_ms=round((time.perf_counter() - start) * 1000),
    )
    return {"retrieved_docs": docs}
