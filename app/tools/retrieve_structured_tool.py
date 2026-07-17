"""Graph tool: structured retrieval over complaints table."""

from __future__ import annotations

import time

from loguru import logger

from app.core.services_container import ServicesContainer
from app.core.state import AgentState


def _guess_product(query: str) -> str | None:
    q = query.lower()
    if "overdraft" in q or "checking" in q or "savings" in q:
        return "Checking or savings account"
    if "credit card" in q or "card" in q:
        return "Credit card"
    if "mortgage" in q:
        return "Mortgage"
    return None


def _guess_keyword(query: str) -> str | None:
    q = query.lower()
    for token in ("overdraft", "fee", "late", "interest", "escrow"):
        if token in q:
            return token
    return None


async def retrieve_structured_tool(state: AgentState, *, services: ServicesContainer) -> AgentState:
    request_id = state.get("request_id")
    user_query = state.get("user_query", "")
    start = time.perf_counter()
    results = await services.retrieval.retrieve_complaints(
        user_query,
        top_k=5,
        product=_guess_product(user_query),
        narrative_keyword=_guess_keyword(user_query),
        request_id=request_id,
    )

    logger.info(
        "retrieve_structured_done",
        event="retrieve_structured",
        node_name="retrieve_structured_tool",
        request_id=request_id,
        result_count=len(results),
        duration_ms=round((time.perf_counter() - start) * 1000),
    )
    return {"structured_results": results}
