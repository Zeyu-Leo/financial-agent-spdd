"""Logging contract: JSON fields, request_id injection, secret redaction,
prompt truncation (Task 1 criterion 6 + Safeguards 3)."""

import json

from app.core.logging import (
    PROMPT_TRUNCATE_LEN,
    bind_request_id,
    configure_logging,
    redact,
    reset_request_id,
    truncate_prompt,
)


def test_json_record_has_required_fields(capsys) -> None:  # type: ignore[no-untyped-def]
    from loguru import logger

    configure_logging("json")
    token = bind_request_id("req-123")
    try:
        logger.info("test.event", event="test.event", duration_ms=12)
    finally:
        reset_request_id(token)

    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)
    for key in ("timestamp", "level", "request_id", "event"):
        assert key in record
    assert record["request_id"] == "req-123"
    assert record["event"] == "test.event"
    assert record["duration_ms"] == 12


def test_request_id_resolves_from_contextvar(capsys) -> None:  # type: ignore[no-untyped-def]
    from loguru import logger

    configure_logging("json")
    token = bind_request_id("ctx-abc")
    try:
        logger.info("no.explicit.id", event="no.explicit.id")
    finally:
        reset_request_id(token)
    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["request_id"] == "ctx-abc"


def test_redact_masks_secret_fields() -> None:
    payload = {
        "Authorization": "Bearer sk-secret",
        "openrouter_api_key": "sk-secret",
        "nested": {"api_key": "sk-secret", "safe": "ok"},
        "messages": [{"key": "sk-secret", "role": "user"}],
    }
    redacted = redact(payload)
    assert redacted["Authorization"] == "***REDACTED***"
    assert redacted["openrouter_api_key"] == "***REDACTED***"
    assert redacted["nested"]["api_key"] == "***REDACTED***"
    assert redacted["nested"]["safe"] == "ok"
    assert redacted["messages"][0]["key"] == "***REDACTED***"
    assert "sk-secret" not in json.dumps(redacted)


def test_truncate_prompt_flags_long_text() -> None:
    short, flag = truncate_prompt("hello")
    assert flag is False and short == "hello"

    long_text = "x" * (PROMPT_TRUNCATE_LEN + 50)
    truncated, flag = truncate_prompt(long_text)
    assert flag is True
    assert len(truncated) == PROMPT_TRUNCATE_LEN
