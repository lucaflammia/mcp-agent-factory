"""SourceAdapter protocol and in-memory implementation.

A SourceAdapter exposes documents with their ACLs, pagination, and a
modification stream so the ingestion pipeline can be driven by change data
capture (CDC) rather than full corpus scans.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator, Protocol


@dataclass
class SourceDocument:
    """A document as returned by a SourceAdapter."""
    source_id: str                  # stable opaque ID for the document
    tenant: str                     # tenant / owner_id — maps to owner_id in the store
    text: str                       # raw text; PII scrub happens in the pipeline
    acl: list[str] = field(default_factory=list)   # access-control labels
    modified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    extra: dict = field(default_factory=dict)       # arbitrary per-source metadata


class SourceAdapter(Protocol):
    """Protocol for document sources."""

    async def list_documents(self) -> AsyncIterator[SourceDocument]:
        """Yield all documents managed by this source."""
        ...  # pragma: no cover

    async def list_modified(self, since: datetime) -> AsyncIterator[SourceDocument]:
        """Yield only documents modified after *since* (for CDC)."""
        ...  # pragma: no cover

    async def list_deleted_ids(self, since: datetime) -> AsyncIterator[str]:
        """Yield source_ids deleted after *since* (for CDC tombstoning)."""
        ...  # pragma: no cover


class InMemorySourceAdapter:
    """SourceAdapter backed by an explicit document list — useful for tests."""

    def __init__(self, documents: list[SourceDocument] | None = None) -> None:
        self._docs: dict[str, SourceDocument] = {}
        self._deleted: dict[str, datetime] = {}
        for doc in (documents or []):
            self._docs[doc.source_id] = doc

    def add(self, doc: SourceDocument) -> None:
        self._docs[doc.source_id] = doc

    def delete(self, source_id: str) -> None:
        self._docs.pop(source_id, None)
        self._deleted[source_id] = datetime.now(timezone.utc)

    async def list_documents(self) -> AsyncIterator[SourceDocument]:
        for doc in list(self._docs.values()):
            yield doc

    async def list_modified(self, since: datetime) -> AsyncIterator[SourceDocument]:
        for doc in list(self._docs.values()):
            if doc.modified_at > since:
                yield doc

    async def list_deleted_ids(self, since: datetime) -> AsyncIterator[str]:
        for sid, deleted_at in list(self._deleted.items()):
            if deleted_at > since:
                yield sid
