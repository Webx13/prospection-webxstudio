"""Journalisation structurée (JSON ou texte lisible) avec masquage systématique."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from blackforge_api.core.redaction import redact_mapping, redact_text

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributs standard d'un LogRecord : tout le reste est considéré comme un champ structuré.
_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
    | {"message", "asctime", "taskName"}
)


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {key: value for key, value in record.__dict__.items() if key not in _RESERVED}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        if (request_id := request_id_var.get()) is not None:
            payload["request_id"] = request_id
        payload.update(redact_mapping(_extra_fields(record)))
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extras = redact_mapping(_extra_fields(record))
        suffix = f" {json.dumps(extras, ensure_ascii=False, default=str)}" if extras else ""
        rid = request_id_var.get()
        prefix = f"[{rid[:8]}] " if rid else ""
        message = redact_text(record.getMessage())
        line = f"{record.levelname:<7} {record.name}: {prefix}{message}{suffix}"
        if record.exc_info:
            line += "\n" + redact_text(self.formatException(record.exc_info))
        return line


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_output else TextFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # uvicorn journalise lui-même ses accès : on garde notre journal d'accès structuré.
    logging.getLogger("uvicorn.access").disabled = True
