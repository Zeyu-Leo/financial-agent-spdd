"""Task 3 state model smoke tests."""

from __future__ import annotations

from datetime import date

from app.core.state import AgentState, ComplaintRow, DocumentChunk


def test_agent_state_round_trip_populated() -> None:
    state: AgentState = {
        "request_id": "req-1",
        "session_id": "s-1",
        "user_query": "question",
        "conversation_history": [{"role": "user", "content": "hi"}],
        "safety_decision": None,
        "retrieved_docs": [
            DocumentChunk(
                chunk_id=1,
                source_file="a.txt",
                title="A",
                section="",
                chunk_index=0,
                raw_text="hello",
                score=0.99,
            )
        ],
        "structured_results": [
            ComplaintRow(
                complaint_id="C1",
                date_received=date(2024, 1, 1),
                product="Credit card",
                sub_product=None,
                issue="Issue",
                sub_issue=None,
                company="Bank",
                state="CA",
                narrative="text",
                company_response="done",
                consumer_disputed="No",
            )
        ],
        "scenario": None,
        "analysis_notes": "notes",
        "final_answer": "answer",
        "error": None,
    }

    assert state["request_id"] == "req-1"
    assert state["retrieved_docs"][0].source_file == "a.txt"
    assert state["structured_results"][0].complaint_id == "C1"
    assert state["analysis_notes"] == "notes"
    assert state["final_answer"] == "answer"
