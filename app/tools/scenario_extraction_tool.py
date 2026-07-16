"""Graph tool: extract structured Scenario from the user query.

Renders ``scenario_extraction.j2``, calls the LLM, and parses the
response into a ``Scenario`` Pydantic model.  On the first JSON parse
failure the tool retries once with ``scenario_extraction.simplified.j2``
(a stripped-down "return only JSON" prompt).  A second failure raises
``LLMOutputValidationError`` — callers must not silently swallow it.
"""

from __future__ import annotations

import re
import time

from loguru import logger
from pydantic import ValidationError

from app.core.exceptions import LLMOutputValidationError, LLMProviderError
from app.core.safety_policy import Scenario
from app.core.services_container import ServicesContainer
from app.core.state import AgentState

# Regex: extract the first JSON object from a string that may contain
# surrounding prose or markdown fences.
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> str:
    """Strip markdown fences and extract the first {...} substring."""
    # Remove ```json ... ``` or ``` ... ``` wrappers
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    m = _JSON_OBJECT_RE.search(cleaned)
    return m.group(0) if m else cleaned


def _parse_scenario(raw: str) -> Scenario | None:
    """Attempt to parse *raw* as a ``Scenario``.  Returns None on failure."""
    try:
        return Scenario.model_validate_json(_extract_json(raw))
    except (ValidationError, ValueError):
        return None


async def scenario_extraction_tool(
    state: AgentState, *, services: ServicesContainer
) -> AgentState:
    """Extract a ``Scenario`` from ``state["user_query"]``.

    Retries once with the simplified prompt on parse failure.
    Raises ``LLMOutputValidationError`` if both attempts fail.
    """
    request_id = state.get("request_id")
    user_query = state.get("user_query", "")
    start = time.perf_counter()

    # --- first attempt ---
    prompt = services.prompts.render(
        "scenario_extraction.j2", {"user_query": user_query}
    )
    try:
        raw1 = await services.llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=400,
            request_id=request_id,
        )
    except LLMProviderError:
        logger.warning(
            "scenario_extraction.llm_error",
            event="scenario_extraction",
            node_name="scenario_extraction_tool",
            request_id=request_id,
            attempt=1,
        )
        raise

    scenario = _parse_scenario(raw1)
    if scenario is not None:
        logger.info(
            "scenario_extraction.done",
            event="scenario_extraction",
            node_name="scenario_extraction_tool",
            request_id=request_id,
            product_type=scenario.product_type,
            issue_type=scenario.issue_type,
            duration_ms=round((time.perf_counter() - start) * 1000),
        )
        return {"scenario": scenario}

    # --- retry with simplified prompt ---
    logger.warning(
        "scenario_extraction.parse_failed_retrying",
        event="scenario_extraction",
        node_name="scenario_extraction_tool",
        request_id=request_id,
        raw_output=raw1[:200],
    )
    simplified_prompt = services.prompts.render(
        "scenario_extraction.simplified.j2",
        {"user_query": user_query, "raw_output": raw1},
    )
    try:
        raw2 = await services.llm.complete(
            messages=[{"role": "user", "content": simplified_prompt}],
            temperature=0.0,
            max_tokens=400,
            request_id=request_id,
        )
    except LLMProviderError:
        logger.warning(
            "scenario_extraction.llm_error",
            event="scenario_extraction",
            node_name="scenario_extraction_tool",
            request_id=request_id,
            attempt=2,
        )
        raise

    scenario = _parse_scenario(raw2)
    if scenario is not None:
        logger.info(
            "scenario_extraction.done_after_retry",
            event="scenario_extraction",
            node_name="scenario_extraction_tool",
            request_id=request_id,
            product_type=scenario.product_type,
            duration_ms=round((time.perf_counter() - start) * 1000),
        )
        return {"scenario": scenario}

    # Both attempts failed — raise with both raw outputs.
    raise LLMOutputValidationError(
        "scenario_extraction_tool failed to parse Scenario after two attempts",
        raw_output=f"attempt_1={raw1!r}\nattempt_2={raw2!r}",
        request_id=request_id,
    )
