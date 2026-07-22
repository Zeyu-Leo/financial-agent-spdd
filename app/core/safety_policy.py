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

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

_US_STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}


# ---------------------------------------------------------------------------
# Scenario — structured intent extracted from the user query
# ---------------------------------------------------------------------------
class Scenario(BaseModel):
    """Structured intent extracted by ``scenario_extraction_tool``.

    ``product_type`` and ``issue_type`` steer retrieval filters and the
    synthesis prompt; they are never shown verbatim to the user.
    """

    model_config = ConfigDict(extra="forbid")

    product_type: Literal[
        "credit_card", "checking_or_savings", "mortgage", "debt_collection", "other"
    ] = Field(description="Financial product inferred from the user query.")
    issue_type: str = Field(
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
        description="Short lowercase slug, e.g. 'overdraft', 'late_fee', 'escrow'.",
    )
    amount: float | None = Field(
        default=None,
        ge=0,
        description="Dollar amount mentioned in the query, or null.",
    )
    jurisdiction: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{2}$",
        description="Two-letter US state code if mentioned, else null.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Extraction confidence between 0.0 and 1.0.",
    )

    @field_validator("jurisdiction", mode="before")
    @classmethod
    def normalise_jurisdiction(cls, value: object) -> object:
        """Accept a state name from legacy/provider output and store its code."""
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return _US_STATE_CODES.get(stripped.lower(), stripped.upper())


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
