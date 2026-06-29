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

    # Always required.
    pg_dsn: str
    llm_provider: Literal["ollama", "openrouter", "portkey"] = "ollama"
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

    # Ollama (canonical local provider).
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "gemma3:27b"
    ollama_ops_model: str = "qwen3.5:4b"

    # Embeddings.
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    @model_validator(mode="after")
    def _require_provider_keys(self) -> "Settings":
        if self.llm_provider == "openrouter" and not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY required when LLM_PROVIDER=openrouter")
        if self.llm_provider == "portkey":
            if not self.portkey_api_key:
                raise ValueError("PORTKEY_API_KEY required when LLM_PROVIDER=portkey")
            if not self.portkey_provider:
                raise ValueError("PORTKEY_PROVIDER required when LLM_PROVIDER=portkey")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values sourced from env / .env
