"""Task 3 graph integration tests with deterministic stubs."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.core.graph import build_agent
from app.core.prompt_service import PromptService
from app.core.state import ComplaintRow, DocumentChunk

FIXTURE_DIR = Path(__file__).parent / "fixtures"
_PROMPTS = PromptService()


class _StubRetrieval:
    def __init__(self, docs: list[DocumentChunk], rows: list[ComplaintRow]) -> None:
        self._docs = docs
        self._rows = rows

    async def retrieve_docs(
        self, query: str, *, top_k: int, request_id: str | None
    ) -> list[DocumentChunk]:
        return self._docs[:top_k]

    async def retrieve_complaints(
        self,
        query: str,
        *,
        top_k: int,
        product: str | None,
        narrative_keyword: str | None,
        request_id: str | None,
    ) -> list[ComplaintRow]:
        return self._rows[:top_k]


_SCENARIO_STUB = '{"product_type":"checking_or_savings","issue_type":"overdraft","amount":null,"jurisdiction":null,"confidence":0.8}'


class _StubLLM:
    def __init__(self) -> None:
        self._analysis = (
            (FIXTURE_DIR / "llm_responses" / "analysis_notes_ok.txt").read_text().strip()
        )
        self._answer = (FIXTURE_DIR / "llm_responses" / "final_answer_ok.txt").read_text().strip()

    async def complete(
        self, messages: list[dict[str, str]], *, request_id: str | None = None, **kwargs: object
    ) -> str:
        prompt = messages[-1]["content"].lower()
        # scenario extraction prompt contains the schema keyword
        if "product_type" in prompt and "issue_type" in prompt:
            return _SCENARIO_STUB
        if "analysis_notes" in prompt:
            return self._answer
        return self._analysis


def _load_docs() -> list[DocumentChunk]:
    payload = json.loads((FIXTURE_DIR / "retrieval" / "overdraft_chunks.json").read_text())
    return [DocumentChunk(**item) for item in payload]


def _load_rows() -> list[ComplaintRow]:
    payload = json.loads((FIXTURE_DIR / "retrieval" / "credit_card_complaints.json").read_text())
    return [ComplaintRow(**item) for item in payload]


async def test_graph_run_populates_required_fields() -> None:
    services = SimpleNamespace(
        retrieval=_StubRetrieval(_load_docs(), _load_rows()),
        llm=_StubLLM(),
        prompts=_PROMPTS,
        settings=SimpleNamespace(
            conversation_compression_threshold=5,
            conversation_compression_keep_tail=2,
            chat_provider="ollama",
            ollama_ops_model="qwen3.5:4b",
        ),
    )
    runner = build_agent(services)

    out = await runner.run(
        user_query="My bank charged an overdraft fee",
        session_id="s-1",
        conversation_history=[],
        request_id="req-graph-1",
    )

    assert out["retrieved_docs"]
    assert out["structured_results"]
    assert out["analysis_notes"]
    assert out["final_answer"]
    assert out.get("error") is None


async def test_graph_empty_retrieval_still_returns_answer() -> None:
    services = SimpleNamespace(
        retrieval=_StubRetrieval([], []),
        llm=_StubLLM(),
        prompts=_PROMPTS,
        settings=SimpleNamespace(
            conversation_compression_threshold=5,
            conversation_compression_keep_tail=2,
            chat_provider="ollama",
            ollama_ops_model="qwen3.5:4b",
        ),
    )
    runner = build_agent(services)

    out = await runner.run(
        user_query="unknown edge case",
        session_id=None,
        conversation_history=[],
        request_id="req-graph-2",
    )

    assert out["final_answer"]
    assert "grounding" in (out["final_answer"] or "").lower()
    assert out.get("error") is None
