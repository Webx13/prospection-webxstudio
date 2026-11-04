from __future__ import annotations

import json
import logging

import pytest

from blackforge_api.core.logging import JsonFormatter, TextFormatter, request_id_var
from blackforge_api.core.redaction import REDACTED, redact_mapping, redact_text


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("connect postgresql+psycopg://admin:hunter2@db:5432/app failed", "hunter2"),
        ("Authorization: Bearer eyJhbGciOi.payload.sig", "eyJhbGciOi"),
        ("retrying with password=correct-horse-battery", "correct-horse-battery"),
        ("api_key: abcd1234efgh5678", "abcd1234efgh5678"),
        ("using key sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWX", "ABCDEFGHIJKLMNOPQRSTUVWX"),
        ("GET /x?access_token=tok_12345&ok=1", "tok_12345"),
    ],
)
def test_redact_text_masks_secrets(raw: str, secret: str) -> None:
    assert secret not in redact_text(raw)
    assert REDACTED in redact_text(raw)


def test_redact_text_leaves_harmless_text_untouched() -> None:
    text = "Projet 'bot-discord' créé en 12 ms (3 fichiers)"
    assert redact_text(text) == text


def test_redact_text_keeps_url_user_and_host() -> None:
    masked = redact_text("postgresql://admin:hunter2@db:5432/app")
    assert masked == f"postgresql://admin:{REDACTED}@db:5432/app"


def test_redact_mapping_masks_by_key_and_recurses() -> None:
    data = {
        "user": "ada",
        "Password": "p1",
        "nested": {"api_key": "k1", "note": "token=zzz-secret-value"},
        "items": [{"authorization": "Bearer abc"}, "plain"],
    }
    masked = redact_mapping(data)
    flat = json.dumps(masked)
    for secret in ("p1", "k1", "zzz-secret-value", "Bearer abc"):
        assert secret not in flat
    assert masked["user"] == "ada"


def _record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, message, None, None)
    record.__dict__.update(extra)
    return record


def test_json_formatter_emits_valid_masked_json_with_request_id() -> None:
    token = request_id_var.set("req-12345678")
    try:
        line = JsonFormatter().format(
            _record("login password=swordfish", token="abc.def", status=200)
        )
    finally:
        request_id_var.reset(token)
    payload = json.loads(line)
    assert payload["request_id"] == "req-12345678"
    assert payload["level"] == "INFO"
    assert payload["status"] == 200
    assert "swordfish" not in line
    assert "abc.def" not in line


def test_json_formatter_masks_secrets_inside_tracebacks() -> None:
    try:
        raise RuntimeError("cannot reach postgresql://svc:topsecret@db/x")
    except RuntimeError:
        import sys

        record = _record("boom")
        record.exc_info = sys.exc_info()
    line = JsonFormatter().format(record)
    assert "topsecret" not in line
    assert "RuntimeError" in json.loads(line)["exception"]


def test_text_formatter_masks_secrets() -> None:
    line = TextFormatter().format(_record("Bearer abcdef0123456789", api_key="k-123"))
    assert "abcdef0123456789" not in line
    assert "k-123" not in line
