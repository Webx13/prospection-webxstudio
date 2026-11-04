"""Masquage des secrets avant qu'ils n'atteignent les journaux.

Deux niveaux : par clé (champs structurés dont le nom est sensible) et par motif
(texte libre : URL avec mot de passe, en-têtes ``Bearer``, ``clé=valeur`` sensibles).
Ce n'est pas une garantie absolue — la règle reste de ne jamais journaliser de secret.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "***"

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "database_url",
    "dsn",
)

_URL_CREDENTIALS = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)(?P<user>[^/\s:@]*):(?P<pw>[^@\s/]+)@"
)
_BEARER = re.compile(r"(?i)\b(?P<kind>bearer|basic)\s+[A-Za-z0-9._~+/\-]+=*")
_KEY_VALUE = re.compile(
    r"(?i)(?P<key>[\w\-]*(?:password|passwd|secret|token|api[_\-]?key|authorization)[\w\-]*)"
    r"(?P<sep>\s*[=:]\s*)(?P<val>[^\s,;&\"']+)"
)
_PROVIDER_KEY = re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{16,}\b")


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def redact_text(text: str) -> str:
    text = _URL_CREDENTIALS.sub(rf"\g<scheme>\g<user>:{REDACTED}@", text)
    text = _BEARER.sub(rf"\g<kind> {REDACTED}", text)
    text = _KEY_VALUE.sub(rf"\g<key>\g<sep>{REDACTED}", text)
    return _PROVIDER_KEY.sub(REDACTED, text)


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, list | tuple):
        return [redact_value(item) for item in value]
    return value


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: REDACTED if is_sensitive_key(str(key)) else redact_value(value)
        for key, value in data.items()
    }
