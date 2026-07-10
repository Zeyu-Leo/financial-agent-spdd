"""Agent orchestration state shared by LangGraph nodes (Task 3).

Task 3 re-exports retrieval row models from Task 2 so graph code imports
state types from one place.
"""

from __future__ import annotations

from typing import Any, TypeAlias, TypedDict

from app.services.retrieval_service import ComplaintRow, DocumentChunk

# Task 3 placeholder aliases. Concrete models land in Task 4/7.
Scenario: TypeAlias = Any
SafetyDecision: TypeAlias = Any


class AgentState(TypedDict, total=False):
    request_id: str
    session_id: str | None
    user_query: str
    conversation_history: list[dict[str, Any]]
    iso_started_at: str
    safety_decision: SafetyDecision | None
    retrieved_docs: list[DocumentChunk]
    structured_results: list[ComplaintRow]
    scenario: Scenario | None
    analysis_notes: str
    final_answer: str | None
    error: str | None


__all__ = [
    "AgentState",
    "ComplaintRow",
    "DocumentChunk",
    "SafetyDecision",
    "Scenario",
]
