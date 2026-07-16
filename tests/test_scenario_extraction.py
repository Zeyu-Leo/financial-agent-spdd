"""Tests for scenario_extraction_tool: happy path, retry, double-failure."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from app.core.exceptions import LLMOutputValidationError, LLMProviderError
from app.core.prompt_service import PromptService
from app.core.safety_policy import Scenario
from app.core.state import AgentState
from app.tools.scenario_extraction_tool import scenario_extraction_tool

_FIXTURES = Path(__file__).parent / "fixtures" / "llm_responses"


def _make_services(llm_complete: AsyncMock) -> SimpleNamespace:
    """Minimal services stub with real PromptService."""
    llm = SimpleNamespace(complete=llm_complete)
    return SimpleNamespace(llm=llm, prompts=PromptService())


def _state(query: str = "I was charged a $35 overdraft fee in California") -> AgentState:
    return {"request_id": "test-req", "user_query": query}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_happy_path_returns_scenario() -> None:
    raw = (_FIXTURES / "scenario_ok.json").read_text()
    svc = _make_services(AsyncMock(return_value=raw))
    result = await scenario_extraction_tool(_state(), services=svc)
    scenario: Scenario = result["scenario"]
    assert scenario.product_type == "checking_or_savings"
    assert scenario.issue_type == "overdraft"
    assert scenario.amount == 35.0
    assert scenario.jurisdiction == "CA"
    assert 0.0 <= scenario.confidence <= 1.0
    svc.llm.complete.assert_called_once()


@pytest.mark.asyncio
async def test_markdown_fence_stripped() -> None:
    """LLM wraps output in ```json fences — should still parse."""
    raw = (_FIXTURES / "scenario_ok.json").read_text().strip()
    fenced = f"```json\n{raw}\n```"
    svc = _make_services(AsyncMock(return_value=fenced))
    result = await scenario_extraction_tool(_state(), services=svc)
    assert isinstance(result["scenario"], Scenario)


# ---------------------------------------------------------------------------
# Retry path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_malformed_first_attempt_retries_and_succeeds() -> None:
    malformed = (_FIXTURES / "scenario_malformed.json").read_text()
    ok_raw = (_FIXTURES / "scenario_ok.json").read_text()
    mock = AsyncMock(side_effect=[malformed, ok_raw])
    svc = _make_services(mock)
    result = await scenario_extraction_tool(_state(), services=svc)
    assert isinstance(result["scenario"], Scenario)
    assert mock.call_count == 2  # first attempt + retry


@pytest.mark.asyncio
async def test_malformed_both_attempts_raises() -> None:
    malformed = (_FIXTURES / "scenario_malformed.json").read_text()
    mock = AsyncMock(side_effect=[malformed, malformed])
    svc = _make_services(mock)
    with pytest.raises(LLMOutputValidationError):
        await scenario_extraction_tool(_state(), services=svc)
    assert mock.call_count == 2


# ---------------------------------------------------------------------------
# LLMProviderError propagates
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_llm_provider_error_propagates() -> None:
    mock = AsyncMock(side_effect=LLMProviderError("down", provider="ollama"))
    svc = _make_services(mock)
    with pytest.raises(LLMProviderError):
        await scenario_extraction_tool(_state(), services=svc)
