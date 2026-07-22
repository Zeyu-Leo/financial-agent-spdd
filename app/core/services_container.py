"""Dependency bundle constructed once in the API lifespan.

A plain dataclass this week; grows real slots (retrieval, feedback) in
later weeks. Constructor-based DI only — no global singletons.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.core.prompt_service import PromptService
from app.core.safety_policy import SafetyPolicy
from app.services.llm_service import LLMService
from app.services.retrieval_service import RetrievalService

if TYPE_CHECKING:
    from app.core.graph import AgentRunner


@dataclass
class ServicesContainer:
    settings: Settings
    llm_service: LLMService
    retrieval: RetrievalService
    prompts: PromptService
    safety: SafetyPolicy
    runner: AgentRunner | None = None

    @property
    def llm(self) -> LLMService:
        """Alias used by orchestration tools (Task 3+)."""
        return self.llm_service
