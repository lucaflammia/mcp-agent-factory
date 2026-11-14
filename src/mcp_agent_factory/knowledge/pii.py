"""PII scrubbing stage for the ingestion pipeline.

Runs before the embedder. Every redaction is written to an in-process audit
log so operators can confirm that PII never reaches the vector store.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("phone_us", re.compile(r"\b(?:\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b")),
    ("ssn", re.compile(r"\b\d{3}[- ]\d{2}[- ]\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ \-]?){13,16}\b")),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]

_PLACEHOLDER = "[REDACTED]"


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@dataclass
class PiiAuditEntry:
    source_id: str
    chunk_ref: str           # e.g. "source_id#position"
    pattern_type: str
    count: int
    scrubbed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PiiAuditLog:
    """In-process append-only audit log for PII redactions."""

    def __init__(self) -> None:
        self._entries: list[PiiAuditEntry] = []

    def record(self, entry: PiiAuditEntry) -> None:
        self._entries.append(entry)

    def entries(self) -> list[PiiAuditEntry]:
        return list(self._entries)

    def entries_for_source(self, source_id: str) -> list[PiiAuditEntry]:
        return [e for e in self._entries if e.source_id == source_id]


# ---------------------------------------------------------------------------
# Scrubber
# ---------------------------------------------------------------------------

class ScrubResult(NamedTuple):
    text: str
    redactions: list[tuple[str, int]]   # (pattern_type, count)


def scrub_pii(text: str) -> ScrubResult:
    """Replace PII patterns with [REDACTED] and return redaction counts."""
    redactions: list[tuple[str, int]] = []
    for pattern_type, pattern in _PATTERNS:
        matches = pattern.findall(text)
        if matches:
            redactions.append((pattern_type, len(matches)))
            text = pattern.sub(_PLACEHOLDER, text)
    return ScrubResult(text=text, redactions=redactions)
