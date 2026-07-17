"""Safety policy models and stub evaluator.

``Scenario`` and ``SafetyDecision`` are the two structured-output
Pydantic models introduced in Task 4.  Both are defined here so
``app/core/state.py`` can re-export them from a single authoritative
location.

``SafetyPolicy`` holds the evaluation contract that Task 7 will
implement.  Task 4 ships a stub that always allows requests so the
graph can be wired end-to-end before the real classifier is ready.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.core.prompt_service import PromptService
    from app.services.llm_service import LLMService

# ---------------------------------------------------------------------------
# Canonical safety categories (shared between the Pydantic model and the
# safety_classification.j2 template — keep them in sync).
# ---------------------------------------------------------------------------
SAFETY_CATEGORIES: tuple[str, ...] = (
    "allowed_public_information",
    "personalised_financial_advice",
    "pii_exposure_or_inference",
    "tos_evasion",
    "unsupported_guarantees",
)


# ---------------------------------------------------------------------------
# Scenario — structured intent extracted from the user query
# ---------------------------------------------------------------------------
class Scenario(BaseModel):
    """Structured intent extracted by ``scenario_extraction_tool``.

    ``product_type`` and ``issue_type`` steer retrieval filters and the
    synthesis prompt; they are never shown verbatim to the user.
    """

    product_type: str = Field(
        description=("One of: credit_card, checking_or_savings, mortgage, debt_collection, other")
    )
    issue_type: str = Field(description="Short slug, e.g. 'overdraft', 'late_fee', 'escrow'.")
    amount: float | None = Field(
        default=None,
        description="Dollar amount mentioned in the query, or null.",
    )
    jurisdiction: str | None = Field(
        default=None,
        description="US state code or full name if mentioned, else null.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Extraction confidence between 0.0 and 1.0.",
    )


# ---------------------------------------------------------------------------
# SafetyDecision — output of the safety classifier
# ---------------------------------------------------------------------------
class SafetyDecision(BaseModel):
    """Decision emitted by ``SafetyPolicy.evaluate``.

    ``category`` uses a Literal so Pydantic rejects any value not in
    ``SAFETY_CATEGORIES`` at parse time — wrong category names are a
    parse failure, not a silent default.
    """

    allowed: bool
    category: Literal[
        "allowed_public_information",
        "personalised_financial_advice",
        "pii_exposure_or_inference",
        "tos_evasion",
        "unsupported_guarantees",
    ]
    reason: str
    user_message: str


# ---------------------------------------------------------------------------
# SafetyPolicy — runtime evaluator (stub in Task 4; real logic in Task 7)
# ---------------------------------------------------------------------------
class SafetyPolicy:
    """Evaluates a user query against the safety policy.

    Task 4 contract: constructor accepts ``llm`` and ``prompt_service``
    so Task 7 can replace the stub body of ``evaluate`` without changing
    call sites.  Both parameters are kept as kw-only; Task 7 may add
    ``session_factory`` and ``model`` as additional kw-only defaults
    without breaking source compatibility.
    """

    def __init__(
        self,
        llm: LLMService,
        prompt_service: PromptService,
    ) -> None:
        self._llm = llm
        self._prompts = prompt_service

    async def evaluate(
        self,
        *,
        user_query: str,  # noqa: ARG002
        request_id: str,  # noqa: ARG002
    ) -> SafetyDecision:
        """Stub: always allows.  Task 7 replaces this body.

        The signature is the stable contract; callers must not inspect
        anything beyond the returned ``SafetyDecision``.
        """
        return SafetyDecision(
            allowed=True,
            category="allowed_public_information",
            reason="not yet enforced",
            user_message="",
        )
