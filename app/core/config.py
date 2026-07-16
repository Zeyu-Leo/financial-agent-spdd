"""Application configuration. Single source of env access.

This module is the ONLY place permitted to read environment variables
(Safeguard 1). Every other module receives a `Settings` instance.
"""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Always required. Chat and embedding pick their provider independently
    # (same provider for both, or different — e.g. Ollama embed + Portkey chat).
    pg_dsn: str
    chat_provider: Literal["ollama", "openrouter", "portkey", "deepseek", "qwen"] = "ollama"
    embedding_provider: Literal["ollama", "openrouter", "portkey", "deepseek", "qwen"] = "ollama"
    log_format: Literal["json", "text"] = "text"

    # OpenRouter. The api key is conditionally required (see validator).
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "gpt-4.1-mini"

    # Portkey LLM gateway (OpenAI-compatible). Routes to an upstream provider
    # selected by `portkey_provider`; observability/caching/fallback live in the
    # gateway rather than in app code. Keys are conditionally required (validator).
    portkey_api_key: str | None = None  # Portkey account key (x-portkey-api-key)
    portkey_provider: str | None = None  # upstream slug, e.g. "openai" (x-portkey-provider)
    portkey_provider_api_key: str | None = None  # upstream key forwarded as Authorization
    portkey_base_url: str = "https://api.portkey.ai/v1"
    portkey_model: str = "gpt-4.1-mini"

    # DeepSeek. The api key is conditionally required (see validator).
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # Qwen / Alibaba DashScope (OpenAI-compatible). The api key is conditionally required.
    qwen_api_key: str | None = None
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"

    # Ollama (canonical local provider).
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "gemma3:27b"
    ollama_ops_model: str = "qwen3.5:4b"

    # Embeddings.
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # Stage-1 Context Engineering: conversation-history compression.
    # Short conversations (len <= threshold) pass through unchanged with no
    # LLM cost. Set to 0 to disable compression entirely.
    conversation_compression_threshold: int = 5
    # Number of most-recent messages to keep verbatim; everything older is
    # summarised into a single system message. Setting to 0 summarises all.
    conversation_compression_keep_tail: int = 2

    @model_validator(mode="after")
    def _require_provider_keys(self) -> "Settings":
        # A provider's keys are required when EITHER axis selects it.
        providers = {self.chat_provider, self.embedding_provider}
        if "openrouter" in providers and not self.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY required when CHAT_PROVIDER or EMBEDDING_PROVIDER=openrouter"
            )
        if "portkey" in providers:
            if not self.portkey_api_key:
                raise ValueError(
                    "PORTKEY_API_KEY required when CHAT_PROVIDER or EMBEDDING_PROVIDER=portkey"
                )
            if not self.portkey_provider:
                raise ValueError(
                    "PORTKEY_PROVIDER required when CHAT_PROVIDER or EMBEDDING_PROVIDER=portkey"
                )
        if "deepseek" in providers and not self.deepseek_api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY required when CHAT_PROVIDER or EMBEDDING_PROVIDER=deepseek"
            )
        if "qwen" in providers and not self.qwen_api_key:
            raise ValueError(
                "QWEN_API_KEY required when CHAT_PROVIDER or EMBEDDING_PROVIDER=qwen"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values sourced from env / .env
