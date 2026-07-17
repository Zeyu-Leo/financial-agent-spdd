"""Task 3 tool unit tests with stub services."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.core.exceptions import LLMProviderError
from app.core.prompt_service import PromptService
from app.core.state import AgentState, ComplaintRow, DocumentChunk
from app.tools.retrieve_docs_tool import retrieve_docs_tool
from app.tools.retrieve_structured_tool import retrieve_structured_tool
from app.tools.summarise_tool import summarise_tool
from app.tools.synthesise_answer_tool import synthesise_answer_tool

_PROMPTS = PromptService()


class _StubRetrieval:
    def __init__(self) -> None:
        self.docs = [
            DocumentChunk(
                chunk_id=1,
                source_file="overdraft_faq.txt",
                title="Overdraft",
                section="",
                chunk_index=0,
                raw_text="overdraft info",
                score=0.9,
            )
        ]
        self.rows = [
            ComplaintRow(
                complaint_id="CFPB-1",
                date_received=date(2024, 1, 1),
                product="Checking or savings account",
                sub_product=None,
                issue="Overdraft",
                sub_issue=None,
                company="Example",
                state="NY",
                narrative="fee issue",
                company_response="Closed",
                consumer_disputed="Yes",
            )
        ]

    async def retrieve_docs(
        self, query: str, *, top_k: int, request_id: str | None
    ) -> list[DocumentChunk]:
        return self.docs[:top_k]

    async def retrieve_complaints(
        self,
        query: str,
        *,
        top_k: int,
        product: str | None,
        narrative_keyword: str | None,
        request_id: str | None,
    ) -> list[ComplaintRow]:
        return self.rows[:top_k]


class _StubLLM:
    def __init__(self, text: str = "ok") -> None:
        self._text = text

    async def complete(
        self, messages: list[dict[str, str]], *, request_id: str | None = None
    ) -> str:
        return self._text


class _FailingLLM:
    async def complete(
        self, messages: list[dict[str, str]], *, request_id: str | None = None
    ) -> str:
        raise LLMProviderError("boom", provider="ollama", request_id=request_id)


@pytest.fixture
def base_state() -> AgentState:
    return {
        "request_id": "req-1",
        "user_query": "overdraft fee",
        "conversation_history": [],
    }


async def test_retrieve_docs_tool_returns_partial_state(base_state: AgentState) -> None:
    services = SimpleNamespace(retrieval=_StubRetrieval())
    out = await retrieve_docs_tool(base_state, services=services)
    assert "retrieved_docs" in out
    assert out["retrieved_docs"][0].source_file == "overdraft_faq.txt"


async def test_retrieve_structured_tool_returns_partial_state(base_state: AgentState) -> None:
    services = SimpleNamespace(retrieval=_StubRetrieval())
    out = await retrieve_structured_tool(base_state, services=services)
    assert "structured_results" in out
    assert out["structured_results"][0].complaint_id == "CFPB-1"


async def test_summarise_tool_uses_llm_when_grounding_exists(base_state: AgentState) -> None:
    services = SimpleNamespace(llm=_StubLLM("analysis notes"), prompts=_PROMPTS)
    state: AgentState = {
        **base_state,
        "retrieved_docs": _StubRetrieval().docs,
        "structured_results": _StubRetrieval().rows,
    }
    out = await summarise_tool(state, services=services)
    assert out["analysis_notes"] == "analysis notes"


async def test_synthesise_tool_returns_fallback_without_grounding(base_state: AgentState) -> None:
    services = SimpleNamespace(llm=_StubLLM("unused"))
    out = await synthesise_answer_tool(base_state, services=services)
    assert "grounding" in (out["final_answer"] or "").lower()


async def test_summarise_tool_propagates_llm_error(base_state: AgentState) -> None:
    services = SimpleNamespace(llm=_FailingLLM(), prompts=_PROMPTS)
    state: AgentState = {
        **base_state,
        "retrieved_docs": _StubRetrieval().docs,
        "structured_results": _StubRetrieval().rows,
    }
    with pytest.raises(LLMProviderError):
        await summarise_tool(state, services=services)
