"""Tests for SafetyDecision model validation and SafetyPolicy stub."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.prompt_service import PromptService
from app.core.safety_policy import SAFETY_CATEGORIES, SafetyDecision, SafetyPolicy, Scenario

_FIXTURES = Path(__file__).parent / "fixtures" / "llm_responses"


# ---------------------------------------------------------------------------
# SafetyDecision model
# ---------------------------------------------------------------------------
def test_allow_decision_round_trip() -> None:
    raw = (_FIXTURES / "safety_decision_allow.json").read_text()
    decision = SafetyDecision.model_validate_json(raw)
    assert decision.allowed is True
    assert decision.category == "allowed_public_information"
    assert decision.user_message == ""


def test_block_decision_round_trip() -> None:
    raw = (_FIXTURES / "safety_decision_block.json").read_text()
    decision = SafetyDecision.model_validate_json(raw)
    assert decision.allowed is False
    assert decision.category == "personalised_financial_advice"
    assert decision.user_message  # non-empty


def test_all_five_categories_are_valid() -> None:
    for cat in SAFETY_CATEGORIES:
        d = SafetyDecision(allowed=True, category=cat, reason="ok", user_message="")
        assert d.category == cat


def test_unknown_category_rejected() -> None:
    with pytest.raises(ValidationError):
        SafetyDecision(
            allowed=True,
            category="made_up_category",
            reason="x",
            user_message="",
        )


def test_five_canonical_categories() -> None:
    assert len(SAFETY_CATEGORIES) == 5


def test_scenario_normalises_full_state_name() -> None:
    scenario = Scenario(
        product_type="checking_or_savings",
        issue_type="overdraft",
        jurisdiction="California",
        confidence=0.8,
    )
    assert scenario.jurisdiction == "CA"


@pytest.mark.parametrize(
    "payload",
    [
        {"product_type": "bank_account", "issue_type": "fee", "confidence": 0.5},
        {"product_type": "credit_card", "issue_type": "late fee", "confidence": 0.5},
        {"product_type": "mortgage", "issue_type": "escrow", "jurisdiction": "Calif.", "confidence": 0.5},
        {"product_type": "other", "issue_type": "fee", "confidence": 0.5, "unexpected": True},
    ],
)
def test_scenario_rejects_invalid_schema_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)


# ---------------------------------------------------------------------------
# SafetyPolicy stub
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stub_always_allows() -> None:
    llm = SimpleNamespace(complete=None)
    policy = SafetyPolicy(llm=llm, prompt_service=PromptService())
    decision = await policy.evaluate(user_query="What are overdraft fees?", request_id="r1")
    assert decision.allowed is True
    assert decision.category == "allowed_public_information"
    assert decision.reason == "not yet enforced"
