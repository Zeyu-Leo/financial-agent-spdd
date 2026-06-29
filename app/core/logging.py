"""Structured logging built on loguru.

Contract (Norms + Acceptance Criteria):
- Every record carries ``request_id``, read from a ContextVar, never
  threaded by hand. The default ``None`` resolves to the bound value at
  log time, never logged as the string ``"null"``.
- ``LOG_FORMAT=json`` emits JSON with at minimum ``timestamp``,
  ``level``, ``request_id``, ``event`` and (where applicable)
  ``duration_ms``. ``text`` emits a readable key-value line.
- Secrets are redacted at this layer (Safeguard 3); prompts are
  truncated to 500 chars with a ``_truncated: true`` flag.
"""

from __future__ import annotations

import json
import sys
from contextvars import ContextVar, Token
from typing import Any

from loguru import logger

# Canonical carrier for the per-request correlation id. Bound once at API
# ingress by middleware; read everywhere else.
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

PROMPT_TRUNCATE_LEN = 500

# Keys whose values must never reach a log sink.
_SECRET_KEYS = {
    "authorization",
    "api_key",
    "openrouter_api_key",
    "x-api-key",
    "key",
    "x-portkey-api-key",
    "portkey_api_key",
    "portkey_provider_api_key",
}
_REDACTED = "***REDACTED***"


def get_request_id() -> str | None:
    """Return the request_id bound to the current context, if any."""
    return _request_id_var.get()


def bind_request_id(request_id: str) -> Token[str | None]:
    """Bind ``request_id`` into the current context.

    Returns the ContextVar ``Token`` so middleware can reset it after the
    request, keeping async contexts isolated.
    """
    return _request_id_var.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Undo a previous :func:`bind_request_id`."""
    _request_id_var.reset(token)


def redact(value: Any) -> Any:
    """Recursively redact secret-looking fields in a dict/list payload."""
    if isinstance(value, dict):
        return {
            k: (_REDACTED if k.lower() in _SECRET_KEYS else redact(v)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def truncate_prompt(text: str) -> tuple[str, bool]:
    """Truncate a prompt to ``PROMPT_TRUNCATE_LEN``.

    Returns ``(text, was_truncated)`` so callers can attach the
    ``_truncated`` flag to the log record.
    """
    if len(text) > PROMPT_TRUNCATE_LEN:
        return text[:PROMPT_TRUNCATE_LEN], True
    return text, False


def _json_sink(message: Any) -> None:
    """Serialise a loguru record to a single JSON line on stdout."""
    record = message.record
    extra = redact(dict(record["extra"]))
    # request_id is always present; resolve from extra → ContextVar → None.
    request_id = extra.pop("request_id", None) or get_request_id()
    payload: dict[str, Any] = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "request_id": request_id,
        "event": extra.pop("event", record["message"]),
        **extra,
    }
    sys.stdout.write(json.dumps(payload, default=str, ensure_ascii=False) + "\n")


def _text_patcher(record: Any) -> None:
    """Ensure every text-mode record exposes a resolved request_id."""
    if not record["extra"].get("request_id"):
        record["extra"]["request_id"] = get_request_id()


def configure_logging(log_format: str) -> None:
    """Install the single global sink for the chosen format.

    Idempotent: removes any previously installed handlers first.
    """
    logger.remove()
    if log_format == "json":
        logger.configure(extra={"request_id": None, "event": None})
        logger.add(_json_sink, level="INFO")
    else:
        logger.configure(extra={"request_id": None}, patcher=_text_patcher)
        logger.add(
            sys.stdout,
            level="INFO",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
                "request_id={extra[request_id]} | {message} | {extra}"
            ),
        )
