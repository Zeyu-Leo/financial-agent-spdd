"""Dependency bundle constructed once in the API lifespan.

A plain dataclass this week; grows real slots (retrieval, feedback) in
later weeks. Constructor-based DI only — no global singletons.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.services.llm_service import LLMService
from app.services.retrieval_service import RetrievalService


@dataclass
class ServicesContainer:
    settings: Settings
    llm_service: LLMService
    retrieval: RetrievalService
