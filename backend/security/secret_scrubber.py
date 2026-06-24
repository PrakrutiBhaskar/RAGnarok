"""
Secret scrubber — removes API keys and secrets from logs, reports, and error messages.
Applied before any content leaves the process (external API calls, log output, reports).
"""

from __future__ import annotations

import re
from typing import Any


# Patterns that identify secrets — ordered from most specific to least specific
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_key",    re.compile(r"sk-[A-Za-z0-9]{20,}", re.IGNORECASE)),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}", re.IGNORECASE)),
    ("pinecone_key",  re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)),
    ("bearer_token",  re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)),
    ("generic_key",   re.compile(r"(?:api[_-]?key|secret|token|password)\s*[=:]\s*\S+", re.IGNORECASE)),
]

_REDACTED = "[REDACTED]"


def scrub(text: str) -> str:
    """Remove detected secrets from a string."""
    for _name, pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


def scrub_dict(data: dict[str, Any], sensitive_keys: set[str] | None = None) -> dict[str, Any]:
    """
    Recursively scrub a dict, replacing values for known sensitive keys
    and scanning string values for secret patterns.
    """
    default_sensitive = {
        "api_key", "apikey", "secret", "password", "token", "authorization",
        "openai_api_key", "anthropic_api_key", "pinecone_api_key", "cohere_api_key",
    }
    sensitive = default_sensitive | (sensitive_keys or set())

    result: dict[str, Any] = {}
    for k, v in data.items():
        key_lower = k.lower().replace("-", "_")
        if key_lower in sensitive:
            result[k] = _REDACTED
        elif isinstance(v, dict):
            result[k] = scrub_dict(v, sensitive_keys)
        elif isinstance(v, str):
            result[k] = scrub(v)
        elif isinstance(v, list):
            result[k] = [
                scrub(item) if isinstance(item, str)
                else scrub_dict(item, sensitive_keys) if isinstance(item, dict)
                else item
                for item in v
            ]
        else:
            result[k] = v
    return result


def scrub_error_message(exc: Exception) -> str:
    """Scrub an exception message before logging or including in a report."""
    return scrub(str(exc))
