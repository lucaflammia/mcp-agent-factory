"""ValidationGate — validates tool arguments against a Pydantic model.

PIIGate — negative-permissions middleware that blocks sensitive fields
from leaving the local network unless explicitly allow-listed via the
``MCP_ALLOWED_FIELDS`` environment variable.
"""
from __future__ import annotations

import os
import re
from typing import Any, Type

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# PII patterns — ordered from most specific to most general
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # API key signatures (sk-..., sk-proj-..., Bearer tokens)
    ("api_key", re.compile(r'\b(sk-[A-Za-z0-9_\-]{20,}|Bearer\s+[A-Za-z0-9\-._~+/]+=*)\b')),
    # JWT-shaped strings (header.payload.signature)
    ("jwt", re.compile(r'\b[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b')),
    # Email addresses
    ("email", re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')),
    # Private IP addresses (RFC 1918)
    ("private_ip", re.compile(
        r'\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}'
        r'|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}'
        r'|192\.168\.\d{1,3}\.\d{1,3})\b'
    )),
]

_REDACTED = "[REDACTED]"


def _default_allow_list() -> frozenset[str]:
    """Field names that bypass PII scrubbing (from MCP_ALLOWED_FIELDS env var)."""
    raw = os.getenv("MCP_ALLOWED_FIELDS", "")
    return frozenset(f.strip() for f in raw.split(",") if f.strip())


def _contains_pii(value: str) -> bool:
    return any(pat.search(value) for _, pat in _PII_PATTERNS)


class PIIViolation(ValueError):
    """Raised when a field value contains PII and is not in the allow-list."""


class PIIGate:
    """Negative-permissions middleware: blocks fields whose values match PII patterns.

    Fields listed in *allow_list* (or ``MCP_ALLOWED_FIELDS`` env var) bypass the
    check and pass through unchanged.

    Raises:
        PIIViolation: if any field value contains PII and is not allow-listed.
    """

    def scrub(
        self,
        args: dict[str, Any],
        allow_list: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        """Return *args* with PII-containing values redacted.

        Raises ``PIIViolation`` on the *first* offending field that is not
        allow-listed, so callers receive a clear rejection rather than silent
        data corruption.
        """
        effective_allow = (allow_list or frozenset()) | _default_allow_list()
        for key, value in args.items():
            if key in effective_allow:
                continue
            if isinstance(value, str) and _contains_pii(value):
                raise PIIViolation(
                    f"Field '{key}' contains sensitive data and is not allow-listed. "
                    "Add it to MCP_ALLOWED_FIELDS if this is intentional."
                )
        return args


class ValidationGate:
    """Validates a dict of arguments against a Pydantic model class.

    Raises ``pydantic.ValidationError`` on failure so callers can catch it
    and return a structured error response.
    """

    def validate(self, model_cls: Type[BaseModel], data: dict[str, Any]) -> BaseModel:
        """Instantiate *model_cls* with *data* and return the validated instance.

        Raises:
            pydantic.ValidationError: if *data* does not conform to *model_cls*.
        """
        return model_cls(**data)
