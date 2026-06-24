"""
Heuristic PII redactor — applied when --redact flag is set.
Scrubs common PII patterns from chunk text before any external LLM calls.
Not a guarantee of compliance; intended as a best-effort safety layer.
"""

from __future__ import annotations

import re


_PII_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # Email addresses
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    # Phone numbers (US and international)
    ("phone", re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE]"),
    # SSN (US)
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    # Credit card numbers (basic pattern)
    ("credit_card", re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"), "[CREDIT_CARD]"),
    # IP addresses
    ("ip_address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP_ADDRESS]"),
    # Dates of birth patterns
    ("dob", re.compile(r"\b(?:DOB|Date of Birth|Born)[:\s]+\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b", re.IGNORECASE), "[DOB]"),
    # Aadhaar (India) — 12 digit number
    ("aadhaar", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b"), "[AADHAAR]"),
    # PAN card (India)
    ("pan", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN]"),
]


def redact(text: str) -> str:
    """Apply all PII patterns to a text string."""
    for _name, pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_chunks(chunks: list[dict]) -> list[dict]:
    """
    Redact PII from the 'text' field of a list of chunk dicts.
    Returns new dicts (does not mutate originals).
    """
    redacted = []
    for chunk in chunks:
        new_chunk = dict(chunk)
        if "text" in new_chunk and isinstance(new_chunk["text"], str):
            new_chunk["text"] = redact(new_chunk["text"])
        redacted.append(new_chunk)
    return redacted
