"""Graph tool: synthesize final user-facing answer."""

from __future__ import annotations

import time

from loguru import logger

from app.core.exceptions import LLMProviderError
from app.core.services_container import ServicesContainer
from app.core.state import AgentState


def _citation_context(state: AgentState) -> str:
    doc_refs = [
        f"{doc.source_file}#{doc.chunk_index}"
        for doc in state.get("retrieved_docs", [])
    ]
    complaint_refs = [
        row.complaint_id
        for row in state.get("structured_results", [])
    ]
    return (
        "doc_refs=" + (", ".join(doc_refs) if doc_refs else "none") + "\n"
        "complaint_ids=" + (", ".join(complaint_refs) if complaint_refs else "none")
    )


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

    # TODO(Task 4): replace with Jinja template answer_synthesis.j2
    prompt = (
        "Write a concise, user-facing answer using only grounded facts. "
        "If evidence is insufficient, say so clearly. Include citation references in prose.\n\n"
        f"<question>\n{state.get('user_query', '')}\n</question>\n\n"
        f"<analysis_notes>\n{state.get('analysis_notes', '')}\n</analysis_notes>\n\n"
        f"<references>\n{_citation_context(state)}\n</references>"
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
