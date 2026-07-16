"""Task 3 LangGraph orchestration: ingest -> retrieve -> analysis -> synthesis."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from functools import partial
from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from loguru import logger

from app.core.conversation_compress import compress_history
from app.core.exceptions import LLMProviderError
from app.core.services_container import ServicesContainer
from app.core.state import AgentState
from app.tools.retrieve_docs_tool import retrieve_docs_tool
from app.tools.retrieve_structured_tool import retrieve_structured_tool
from app.tools.scenario_extraction_tool import scenario_extraction_tool
from app.tools.summarise_tool import summarise_tool
from app.tools.synthesise_answer_tool import synthesise_answer_tool


async def history_compression_phase(
    state: AgentState, *, services: ServicesContainer
) -> AgentState:
    """Compress conversation_history above the configured threshold.

    Trade-off: compression is a cost optimisation, not a correctness gate.
    If the ops-LLM raises ``LLMProviderError``, this node logs a warning
    and returns ``{}`` so the graph continues with the uncompressed history.
    The helper itself raises; the catch lives here so the decision is
    visible and auditable at the call site.
    """
    try:
        result = await compress_history(
            state.get("conversation_history") or [],
            current_user_query=state.get("user_query", ""),
            llm=services.llm,
            prompts=services.prompts,
            settings=services.settings,
            request_id=state.get("request_id"),
        )
    except LLMProviderError:
        logger.warning(
            "history_compression.failed_skipping",
            event="history_compression_phase",
            node_name="history_compression_phase",
            request_id=state.get("request_id"),
        )
        return {}

    if result.summary is None:
        return {}  # no-op: history was below threshold

    return {"conversation_history": result.messages}


def ingest_input(state: AgentState) -> AgentState:
    request_id = state.get("request_id") or str(uuid.uuid4())
    return {
        "request_id": request_id,
        "safety_decision": None,
        "iso_started_at": datetime.now(tz=UTC).isoformat(),
    }


async def retrieve_phase(state: AgentState, *, services: ServicesContainer) -> AgentState:
    request_id = state.get("request_id")
    doc_result, structured_result = await asyncio.gather(
        retrieve_docs_tool(state, services=services),
        retrieve_structured_tool(state, services=services),
        return_exceptions=True,
    )

    out: AgentState = {}
    failures: list[str] = []

    if isinstance(doc_result, Exception):
        failures.append("docs")
        logger.warning(
            "retrieve_docs_branch_failed",
            event="retrieve_phase",
            node_name="retrieve_phase",
            request_id=request_id,
            error=str(doc_result),
        )
        out["retrieved_docs"] = []
    else:
        out.update(doc_result)

    if isinstance(structured_result, Exception):
        failures.append("structured")
        logger.warning(
            "retrieve_structured_branch_failed",
            event="retrieve_phase",
            node_name="retrieve_phase",
            request_id=request_id,
            error=str(structured_result),
        )
        out["structured_results"] = []
    else:
        out.update(structured_result)

    if len(failures) == 2:
        out["error"] = "Both retrieval branches failed"

    return out


async def analysis_phase(state: AgentState, *, services: ServicesContainer) -> AgentState:
    if state.get("error"):
        return {}
    # Step 1: extract structured intent before summarising
    try:
        scenario_update = await scenario_extraction_tool(state, services=services)
        state = {**state, **scenario_update}
    except LLMProviderError:
        raise
    # Step 2: summarise retrieved evidence
    try:
        return await summarise_tool(state, services=services)
    except LLMProviderError:
        raise


async def synthesis_phase(state: AgentState, *, services: ServicesContainer) -> AgentState:
    if state.get("error"):
        return {}
    try:
        return await synthesise_answer_tool(state, services=services)
    except LLMProviderError:
        raise


def _route_after_retrieve(state: AgentState) -> str:
    if state.get("error"):
        return "stop"
    return "continue"


class AgentRunner:
    def __init__(self, graph: Any) -> None:
        self._graph = graph

    async def run(
        self,
        *,
        user_query: str,
        session_id: str | None,
        conversation_history: list[dict[str, Any]] | None = None,
        request_id: str | None = None,
    ) -> AgentState:
        initial_state: AgentState = {
            "request_id": request_id or str(uuid.uuid4()),
            "session_id": session_id,
            "user_query": user_query,
            "conversation_history": conversation_history or [],
            "safety_decision": None,
            "scenario": None,
            "error": None,
        }
        output = await self._graph.ainvoke(initial_state)
        return cast(AgentState, output)


def build_agent(services: ServicesContainer) -> AgentRunner:
    graph = StateGraph(AgentState)
    graph.add_node("ingest_input", ingest_input)
    graph.add_node(
        "history_compression_phase",
        partial(history_compression_phase, services=services),
    )
    graph.add_node("retrieve_phase", partial(retrieve_phase, services=services))
    graph.add_node("analysis_phase", partial(analysis_phase, services=services))
    graph.add_node("synthesis_phase", partial(synthesis_phase, services=services))

    graph.add_edge(START, "ingest_input")
    graph.add_edge("ingest_input", "history_compression_phase")
    graph.add_edge("history_compression_phase", "retrieve_phase")
    graph.add_conditional_edges(
        "retrieve_phase",
        _route_after_retrieve,
        {
            "continue": "analysis_phase",
            "stop": END,
        },
    )
    graph.add_edge("analysis_phase", "synthesis_phase")
    graph.add_edge("synthesis_phase", END)

    return AgentRunner(graph.compile())
