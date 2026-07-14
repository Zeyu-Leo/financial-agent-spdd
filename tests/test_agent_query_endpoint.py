"""Task 3 API endpoint tests for /agent/query."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class _RunnerOK:
    async def run(
        self,
        *,
        user_query: str,
        session_id: str | None,
        conversation_history: list[dict],
        request_id: str | None = None,
    ) -> dict:
        return {
            "request_id": request_id,
            "retrieved_docs": [],
            "structured_results": [],
            "analysis_notes": "No relevant grounding found in retrieval results.",
            "final_answer": "I could not find relevant grounding in the current policy and complaint corpora.",
            "error": None,
        }


class _RunnerHappy:
    async def run(
        self,
        *,
        user_query: str,
        session_id: str | None,
        conversation_history: list[dict],
        request_id: str | None = None,
    ) -> dict:
        from app.services.retrieval_service import ComplaintRow, DocumentChunk

        doc = DocumentChunk(
            chunk_id=1,
            source_file="overdraft_faq.txt",
            title="Overdraft",
            section="",
            chunk_index=0,
            raw_text="x",
            score=0.9,
        )
        row = ComplaintRow(
            complaint_id="CFPB-1",
            date_received="2024-01-01",
            product="Checking or savings account",
            sub_product=None,
            issue="Overdraft",
            sub_issue=None,
            company="Example",
            state="CA",
            narrative="n",
            company_response="r",
            consumer_disputed="Yes",
        )
        return {
            "request_id": request_id,
            "retrieved_docs": [doc],
            "structured_results": [row],
            "analysis_notes": "notes",
            "final_answer": "answer",
            "error": None,
        }


class _RunnerLLMError:
    async def run(
        self,
        *,
        user_query: str,
        session_id: str | None,
        conversation_history: list[dict],
        request_id: str | None = None,
    ) -> dict:
        from app.core.exceptions import LLMProviderError

        raise LLMProviderError("provider down", provider="ollama", request_id=request_id)


@pytest.fixture

def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PG_DSN", "postgresql+psycopg://x")
    monkeypatch.setenv("CHAT_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")

    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.api.main import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_agent_query_happy_path(client: TestClient) -> None:
    client.app.state.container.runner = _RunnerHappy()
    resp = client.post("/agent/query", json={"question": "overdraft fee"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_answer"]
    assert body["retrieved_doc_ids"] == ["overdraft_faq.txt#0"]
    assert body["retrieved_complaint_ids"] == ["CFPB-1"]
    assert resp.headers.get("X-Request-Id")


def test_agent_query_empty_retrieval_path(client: TestClient) -> None:
    client.app.state.container.runner = _RunnerOK()
    resp = client.post("/agent/query", json={"question": "unmatched query"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_answer"]
    assert "grounding" in body["final_answer"].lower()


def test_agent_query_llm_error_path(client: TestClient) -> None:
    client.app.state.container.runner = _RunnerLLMError()
    resp = client.post("/agent/query", json={"question": "overdraft fee"})
    assert resp.status_code == 502
    body = resp.json()
    assert body["error_code"] == "llm_provider_error"
    assert body["request_id"]
