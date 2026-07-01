"""
Single source of truth for "current UTC time" across the codebase.

Two problems this solves at once:

1. `datetime.datetime.utcnow()` is deprecated (Python 3.12+) in favor of
   `datetime.now(timezone.utc)`. We use the latter internally.

2. Every timestamp column in this schema is a naive `DateTime` (no
   `timezone=True`) for simplicity and SQLite compatibility, so we strip
   tzinfo before returning — keeping every caller naive-UTC-consistent
   without a wider migration to timezone-aware columns.

3. ORM defaults previously used `sqlalchemy.func.now()`, which on SQLite
   resolves via `CURRENT_TIMESTAMP` — only second-level precision. Two
   rows inserted within the same second (e.g. two sessions created back
   to back) get identical `created_at` values, making `ORDER BY
   created_at DESC` non-deterministic between them. Using this
   Python-side callable as the default instead gives microsecond
   precision on every backend.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time, timezone-naive, microsecond precision."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
