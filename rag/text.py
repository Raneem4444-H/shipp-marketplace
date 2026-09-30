"""Text cleaning + PII redaction, with a Python version and an identical Spark version.

Spec §9.1: emails and phone numbers must not reach Silver, Gold, AI Search or the Agent.
Both versions use the SAME regexes (defined once here), and a unit test checks they agree.
"""

import re
from typing import Optional

EMAIL_PATTERN = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
# 9+ digits, optionally separated by single spaces/dots/dashes/brackets, optional leading '+'.
# Catches +971 50 123 4567 and 0501234567; leaves dates (2026-12-15) and sizes (120x80) alone.
PHONE_PATTERN = r"\+?\d(?:[\s().-]?\d){8,}"
REDACTED = "[redacted]"

_EMAIL_RE = re.compile(EMAIL_PATTERN)
_PHONE_RE = re.compile(PHONE_PATTERN)
_SPACE_RE = re.compile(r"\s+")


def clean_text(value: Optional[str], max_chars: int) -> Optional[str]:
    """Redact PII, collapse whitespace, trim, cut to max_chars. Empty -> None."""
    if value is None:
        return None
    text = _EMAIL_RE.sub(REDACTED, str(value))
    text = _PHONE_RE.sub(REDACTED, text)
    text = _SPACE_RE.sub(" ", text).strip()[:max_chars]
    return text or None


def contains_pii(value: Optional[str]) -> bool:
    return bool(value) and bool(_EMAIL_RE.search(value) or _PHONE_RE.search(value))


def clean_text_col(col, max_chars: int):
    """Spark twin of clean_text. Takes a Column, returns a Column (NULL when empty)."""
    from pyspark.sql import functions as F

    c = F.regexp_replace(col, EMAIL_PATTERN, REDACTED)
    c = F.regexp_replace(c, PHONE_PATTERN, REDACTED)
    c = F.trim(F.regexp_replace(c, r"\s+", " "))
    c = F.substring(c, 1, max_chars)
    return F.when(F.length(c) > 0, c)


def pii_rows_filter(col):
    """Spark predicate: True where the column still contains an email or phone number."""
    return col.rlike(EMAIL_PATTERN) | col.rlike(PHONE_PATTERN)
