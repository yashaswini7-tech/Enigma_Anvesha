"""Mask personal identifiers before any text leaves the process (e.g. to an LLM)."""

from __future__ import annotations

import re

# Order matters: specific patterns run before the generic account-number pattern.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("[EMAIL]", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("[UPI_ID]", re.compile(r"\b[\w.-]+@[A-Za-z]{2,}\b")),
    ("[PAN]", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)),
    ("[AADHAAR]", re.compile(r"(?<![\dXx])\d{4}[ -]\d{4}[ -]\d{4}(?![\dXx])|\b\d{12}\b")),
    ("[PHONE]", re.compile(r"(?:\+91[\s-]?|\b0)?(?<!\d)[6-9]\d{4}[\s-]?\d{5}\b")),
    ("[ACCT]", re.compile(r"(?<![\w])(?=[0-9Xx*]*\d)[0-9Xx*]{6,}(?![\w])")),
]


def redact(text: str) -> str:
    """Replace emails, UPI IDs, PAN, Aadhaar, phone and account/card/policy numbers."""
    out = str(text)
    for token, pattern in PATTERNS:
        out = pattern.sub(token, out)
    return out


def contains_identifier(text: str) -> bool:
    return any(p.search(str(text)) for _, p in PATTERNS)
