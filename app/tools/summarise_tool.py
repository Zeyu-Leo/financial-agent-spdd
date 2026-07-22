"""Graph tool: create analysis notes from retrieved grounding."""

from __future__ import annotations

import time

from loguru import logger

from app.core.exceptions import LLMProviderError
from app.core.services_container import ServicesContainer
from app.core.state import AgentState


async def summarise_tool(state: AgentState, *, services: ServicesContainer) -> AgentState:
    request_id = state.get("request_id")
    start = time.perf_counter()
    if not state.get("retrieved_docs") and not state.get("structured_results"):
        notes = "No relevant grounding found in retrieval results."
        logger.info(
            "summarise_done_without_grounding",
            event="summarise",
            node_name="summarise_tool",
            request_id=request_id,
            duration_ms=round((time.perf_counter() - start) * 1000),
        )
        return {"analysis_notes": notes}

    prompt = services.prompts.render(
        "doc_summary.j2",
        {
            "user_query": state.get("user_query", ""),
            "retrieved_docs": state.get("retrieved_docs", []),
            "structured_results": state.get("structured_results", []),
        },
    )

    try:
        notes = await services.llm.complete(
            messages=[
                {"role": "system", "content": "Generate grounded analysis notes."},
                {"role": "user", "content": prompt},
            ],
            request_id=request_id,
        )
    except LLMProviderError:
        logger.warning(
            "summarise_failed",
            event="summarise",
            node_name="summarise_tool",
            request_id=request_id,
            duration_ms=round((time.perf_counter() - start) * 1000),
        )
        raise

    logger.info(
        "summarise_done",
        event="summarise",
        node_name="summarise_tool",
        request_id=request_id,
        duration_ms=round((time.perf_counter() - start) * 1000),
    )
    return {"analysis_notes": notes}
