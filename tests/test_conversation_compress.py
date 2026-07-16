"""Tests for compress_history helper — Stage-1 Context Engineering."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.core.conversation_compress import (
    CompressedHistory,
    _SUMMARY_PREFIX,
    compress_history,
)
from app.core.exceptions import LLMProviderError
from app.core.prompt_service import PromptService


def _settings(**overrides: int) -> Settings:
    base = dict(
        pg_dsn="postgresql+psycopg://x:x@localhost/x",
        conversation_compression_threshold=5,
        conversation_compression_keep_tail=2,
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _msgs(n: int) -> list[dict]:
    return [{"role": "user", "content": f"turn {i}"} for i in range(n)]


@pytest.fixture
def prompts() -> PromptService:
    return PromptService()


# ---------------------------------------------------------------------------
# (a) below threshold — no-op, no LLM call
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_below_threshold_noop(prompts: PromptService) -> None:
    msgs = _msgs(3)  # threshold=5
    llm = AsyncMock()
    result = await compress_history(
        msgs, current_user_query="q", llm=llm, prompts=prompts, settings=_settings()
    )
    assert result.summary is None
    assert result.messages is msgs
    llm.complete.assert_not_called()


# ---------------------------------------------------------------------------
# (b) at threshold — no-op (len == threshold means NOT above)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_at_threshold_noop(prompts: PromptService) -> None:
    msgs = _msgs(5)  # exactly at threshold=5
    llm = AsyncMock()
    result = await compress_history(
        msgs, current_user_query="q", llm=llm, prompts=prompts, settings=_settings()
    )
    assert result.summary is None
    llm.complete.assert_not_called()


# ---------------------------------------------------------------------------
# (c) above threshold — success, prefix correct, verbatim tail preserved
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_above_threshold_compresses_and_preserves_tail(
    prompts: PromptService,
) -> None:
    msgs = _msgs(8)  # > threshold=5
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="compressed summary")

    result = await compress_history(
        msgs, current_user_query="q", llm=llm, prompts=prompts, settings=_settings()
    )

    assert result.summary == "compressed summary"
    assert len(result.messages) == 3  # 1 summary + 2 tail
    assert result.messages[0]["role"] == "system"
    assert result.messages[0]["content"].startswith(_SUMMARY_PREFIX)
    assert result.messages[0]["content"] == _SUMMARY_PREFIX + "compressed summary"
    assert result.messages[1:] == msgs[-2:]  # verbatim tail
    llm.complete.assert_called_once()

    # ops-class model must be used (not synthesis model)
    call_kwargs = llm.complete.call_args.kwargs
    assert call_kwargs.get("temperature") == 0.0


# ---------------------------------------------------------------------------
# (d) threshold=0 disables compression
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_threshold_zero_disables(prompts: PromptService) -> None:
    msgs = _msgs(20)
    llm = AsyncMock()
    result = await compress_history(
        msgs,
        current_user_query="q",
        llm=llm,
        prompts=prompts,
        settings=_settings(conversation_compression_threshold=0),
    )
    assert result.summary is None
    llm.complete.assert_not_called()


# ---------------------------------------------------------------------------
# (e) keep_tail=0 — summarise all messages
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_keep_tail_zero_summarises_all(prompts: PromptService) -> None:
    msgs = _msgs(8)
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="full summary")

    result = await compress_history(
        msgs,
        current_user_query="q",
        llm=llm,
        prompts=prompts,
        settings=_settings(conversation_compression_keep_tail=0),
    )
    assert result.summary == "full summary"
    assert len(result.messages) == 1  # only the summary message
    assert result.messages[0]["content"].startswith(_SUMMARY_PREFIX)


# ---------------------------------------------------------------------------
# (f) negative keep_tail raises ValueError
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_negative_keep_tail_raises(prompts: PromptService) -> None:
    with pytest.raises(ValueError, match="keep_tail"):
        await compress_history(
            _msgs(8),
            current_user_query="q",
            llm=AsyncMock(),
            prompts=prompts,
            settings=_settings(conversation_compression_keep_tail=-1),
        )


# ---------------------------------------------------------------------------
# (g) LLMProviderError propagates from helper
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_llm_provider_error_propagates(prompts: PromptService) -> None:
    llm = AsyncMock()
    llm.complete = AsyncMock(
        side_effect=LLMProviderError("ops LLM down", provider="ollama")
    )
    with pytest.raises(LLMProviderError):
        await compress_history(
            _msgs(8),
            current_user_query="q",
            llm=llm,
            prompts=prompts,
            settings=_settings(),
        )
