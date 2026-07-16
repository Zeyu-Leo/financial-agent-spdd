"""Graph tool: synthesize final user-facing answer."""

from __future__ import annotations

import time

from loguru import logger

from app.core.exceptions import LLMProviderError
from app.core.services_container import ServicesContainer
from app.core.state import AgentState


async def synthesise_answer_tool(
    state: AgentState, *, services: ServicesContainer
) -> AgentState:
    request_id = state.get("request_id")
    start = time.perf_counter()

    if not state.get("retrieved_docs") and not state.get("structured_results"):
        answer = (
            "I could not find relevant grounding in the current policy and complaint corpora "
            "for your question. Please share more details or a narrower context so I can retry."
        )
        logger.info(
            "synthesise_done_without_grounding",
            event="synthesise",
            node_name="synthesise_answer_tool",
            request_id=request_id,
            duration_ms=round((time.perf_counter() - start) * 1000),
        )
        return {"final_answer": answer}

    prompt = services.prompts.render(
        "next_steps.j2",
        {
            "user_query": state.get("user_query", ""),
            "analysis_notes": state.get("analysis_notes", ""),
            "retrieved_docs": state.get("retrieved_docs", []),
            "structured_results": state.get("structured_results", []),
            "scenario": state.get("scenario"),
        },
    )

    try:
        answer = await services.llm.complete(
            messages=[
                {"role": "system", "content": "Answer as a grounded financial helpdesk assistant."},
                {"role": "user", "content": prompt},
            ],
            request_id=request_id,
        )
    except LLMProviderError:
        logger.warning(
            "synthesise_failed",
            event="synthesise",
            node_name="synthesise_answer_tool",
            request_id=request_id,
            duration_ms=round((time.perf_counter() - start) * 1000),
        )
        raise

    logger.info(
        "synthesise_done",
        event="synthesise",
        node_name="synthesise_answer_tool",
        request_id=request_id,
        duration_ms=round((time.perf_counter() - start) * 1000),
    )
    return {"final_answer": answer}
