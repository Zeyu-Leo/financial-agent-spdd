"""Typed exceptions for the LLM boundary.

Callers branch on exception *type*, never on parsing error-message
strings (Approach decision 4). Both exceptions serialise their payload
safely when printed so a stray ``str(exc)`` never dumps a giant or
non-serialisable body into a log line.
"""

from __future__ import annotations

import json
from typing import Any


def _safe_repr(payload: Any) -> str:
    """Render an arbitrary payload as a compact, bounded string.

    Never raises: falls back to ``repr`` for non-JSON-serialisable
    objects, and truncates so a multi-KB provider body cannot blow up a
    log record.
    """
    try:
        rendered = json.dumps(payload, default=repr, ensure_ascii=False)
    except (TypeError, ValueError):
        rendered = repr(payload)
    if len(rendered) > 500:
        return rendered[:500] + "...[truncated]"
    return rendered


class LLMProviderError(Exception):
    """Raised when a provider call fails terminally (after retries).

    Carries enough context to debug a failure in later weeks without
    re-running the request.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        payload: Any = None,
        request_id: str | None = None,
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.payload = payload
        self.request_id = request_id
        super().__init__(message)

    def __str__(self) -> str:
        base = super().__str__()
        return (
            f"{base} "
            f"[provider={self.provider} status_code={self.status_code} "
            f"request_id={self.request_id} payload={_safe_repr(self.payload)}]"
        )


class LLMOutputValidationError(Exception):
    """Raised when a structured LLM output fails Pydantic validation.

    Defined here but exercised from Task 4. Carries the raw model output
    verbatim so the parse failure is debuggable; no silent fallback.
    """

    def __init__(
        self,
        message: str,
        *,
        raw_output: str,
        request_id: str | None = None,
    ) -> None:
        self.raw_output = raw_output
        self.request_id = request_id
        super().__init__(message)

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} [request_id={self.request_id} raw_output={_safe_repr(self.raw_output)}]"
