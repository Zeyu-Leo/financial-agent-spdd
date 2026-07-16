"""Stage-1 Context Engineering: conversation-history compression.

``compress_history`` collapses older conversation turns into a single
summary message when the history length exceeds a configurable threshold.
The most recent ``keep_tail`` turns are preserved verbatim because they
carry the highest-signal context for grounded follow-up answers.

Design decisions:
- The helper is decoupled from ``AgentState`` so it can be re-used from
  other code paths (Task 8 Sub-Task D).
- The helper *raises* on LLM failure; the graph node is the only catch
  boundary (best-effort trade-off documented there).
- Compression uses the ops-class model, never the synthesis model.
- The summary message role is ``"system"`` and its content starts with
  the literal prefix ``"[summary of earlier turns] "`` — tests and
  downstream tooling grep for this exact string.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.prompt_service import PromptService
from app.services.llm_service import LLMService

_SUMMARY_PREFIX = "[summary of earlier turns] "


@dataclass(frozen=True)
class CompressedHistory:
    """Return value of :func:`compress_history`.

    ``messages`` is the new ``conversation_history`` list to write back
    into ``AgentState``.  ``summary`` is the prose text produced by the
    ops-model, or ``None`` when compression was a no-op.
    """

    messages: list[dict[str, Any]]
    summary: str | None


def _ops_model(settings: Settings) -> str:
    """Return the ops-class model name for the active chat provider."""
    provider = settings.chat_provider
    if provider == "ollama":
        return settings.ollama_ops_model
    if provider == "openrouter":
        return settings.openrouter_model
    if provider == "portkey":
        return settings.portkey_model
    if provider == "deepseek":
        return settings.deepseek_model
    if provider == "qwen":
        return settings.qwen_model
    return settings.ollama_ops_model


async def compress_history(
    messages: list[dict[str, Any]],
    *,
    current_user_query: str,
    llm: LLMService,
    prompts: PromptService,
    settings: Settings,
    request_id: str | None = None,
) -> CompressedHistory:
    """Compress *messages* if they exceed the configured threshold.

    Parameters
    ----------
    messages:
        The full ``conversation_history`` list.
    current_user_query:
        The user's current question — passed to the template for context
        but not answered by the compression model.
    llm:
        ``LLMService`` instance used for the ops-model call.
    prompts:
        ``PromptService`` used to render ``compress_history.j2``.
    settings:
        ``Settings`` instance supplying threshold, keep_tail, and model.
    request_id:
        Forwarded to ``LLMService.complete`` for tracing.

    Returns
    -------
    CompressedHistory
        ``messages`` unchanged and ``summary=None`` when below threshold
        (no-op).  Otherwise ``messages=[summary_msg, *tail]`` and
        ``summary=<prose text>``.

    Raises
    ------
    ValueError
        When ``keep_tail`` is negative.
    LLMProviderError
        When the ops-model call fails.  The caller (graph node) decides
        whether to swallow or propagate.
    """
    threshold = settings.conversation_compression_threshold
    keep_tail = settings.conversation_compression_keep_tail

    if keep_tail < 0:
        raise ValueError(f"conversation_compression_keep_tail must be >= 0, got {keep_tail}")

    # No-op conditions: threshold disabled, history too short, or tail
    # covers the entire history (nothing left to summarise).
    if threshold == 0 or len(messages) <= threshold or keep_tail >= len(messages):
        return CompressedHistory(messages=messages, summary=None)

    older = messages[:-keep_tail] if keep_tail > 0 else messages
    tail = messages[-keep_tail:] if keep_tail > 0 else []

    prompt = prompts.render(
        "compress_history.j2",
        {
            "older_messages": older,
            "current_user_query": current_user_query,
        },
    )

    # Raises LLMProviderError on failure — intentionally not caught here.
    summary_text = await llm.complete(
        messages=[{"role": "user", "content": prompt}],
        model=_ops_model(settings),
        temperature=0.0,
        max_tokens=300,
        request_id=request_id,
    )

    summary_msg: dict[str, Any] = {
        "role": "system",
        "content": _SUMMARY_PREFIX + summary_text.strip(),
    }

    return CompressedHistory(
        messages=[summary_msg, *tail],
        summary=summary_text.strip(),
    )
