"""Graph tool: create analysis notes from retrieved grounding."""

from __future__ import annotations

import time

from loguru import logger

from app.core.exceptions import LLMProviderError
from app.core.services_container import ServicesContainer
from app.core.state import AgentState


def _doc_facts(state: AgentState) -> str:
    docs = state.get("retrieved_docs", [])
    if not docs:
        return "(none)"
    lines = [
        f"- {doc.source_file}#{doc.chunk_index}: {doc.raw_text[:220]}"
        for doc in docs
    ]
    return "\n".join(lines)


def _complaint_facts(state: AgentState) -> str:
    rows = state.get("structured_results", [])
    if not rows:
        return "(none)"
    lines = [
        f"- {row.complaint_id}: product={row.product}; issue={row.issue}; narrative={((row.narrative or '')[:180])}"
        for row in rows
    ]
    return "\n".join(lines)


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

    # TODO(Task 4): replace with Jinja template doc_summary.j2
    prompt = (
        "You are an analyst for a financial helpdesk. Summarize grounded facts only.\n"
        "Return concise bullet points. If evidence conflicts, mention uncertainty.\n\n"
        f"<question>\n{state.get('user_query', '')}\n</question>\n\n"
        f"<docs>\n{_doc_facts(state)}\n</docs>\n\n"
        f"<complaints>\n{_complaint_facts(state)}\n</complaints>"
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
