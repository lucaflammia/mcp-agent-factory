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


class FileSourceAdapter:
    """SourceAdapter that reads a single file from disk (PDF or plain text).

    PDF extraction requires ``pymupdf`` (``import fitz``) or falls back to
    ``pypdf`` if available, otherwise reads as plain text.
    """

    def __init__(self, path: str, tenant: str, source_id: str | None = None) -> None:
        self._path = path
        self._tenant = tenant
        self._source_id = source_id or path

    def _read_text(self) -> str:
        path = self._path
        if path.lower().endswith(".pdf"):
            try:
                import fitz  # pymupdf
                doc = fitz.open(path)
                return "\n".join(page.get_text() for page in doc)
            except ImportError:
                pass
            try:
                from pypdf import PdfReader
                reader = PdfReader(path)
                return "\n".join(p.extract_text() or "" for p in reader.pages)
            except ImportError:
                pass
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()

    async def list_documents(self) -> AsyncIterator[SourceDocument]:
        text = self._read_text()
        yield SourceDocument(
            source_id=self._source_id,
            tenant=self._tenant,
            text=text,
            extra={"source_type": "pdf" if self._path.lower().endswith(".pdf") else "default"},
        )

    async def list_modified(self, since: datetime) -> AsyncIterator[SourceDocument]:
        import os
        mtime = datetime.fromtimestamp(os.path.getmtime(self._path), tz=timezone.utc)
        if mtime > since:
            async for doc in self.list_documents():
                yield doc

    async def list_deleted_ids(self, since: datetime) -> AsyncIterator[str]:
        return
        yield  # make it an async generator


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
