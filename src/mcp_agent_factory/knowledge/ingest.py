"""
Ingestion pipeline — RAG-02 idempotent implementation.

Stage sequence:
  source adapter (list_documents / list_modified)
    → PII scrub + redaction audit log
    → recursive structure-aware chunker (per-source-type config)
    → embedder (batched, idempotent on content_hash)
    → vector store upsert (ON CONFLICT skip)

Each stage is wrapped in an OTel span. The pipeline is safe to re-run: chunks
already present in the store (same tenant + content_hash) are skipped.

IngestionWorker (backward-compat) is kept for the message-bus event-driven path.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from mcp_agent_factory.gateway.telemetry import get_tracer
from mcp_agent_factory.knowledge.chunker import (
    CHUNKER_CONFIGS,
    ChunkerConfig,
    chunk_document,
    chunk_text,
    validate_chunk_metadata,
)
from mcp_agent_factory.knowledge.pii import PiiAuditEntry, PiiAuditLog, scrub_pii
from mcp_agent_factory.knowledge.source import SourceAdapter, SourceDocument

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Idempotent ingestion pipeline (RAG-02)
# ---------------------------------------------------------------------------

class IdempotentIngestionPipeline:
    """Full ingestion pipeline with PII scrubbing, idempotency, and OTel tracing.

    Usage::

        pipeline = IdempotentIngestionPipeline(
            store=store,
            embedder=embedder,
            embedder_id="all-MiniLM-L6-v2@v1",
        )
        stats = await pipeline.ingest(adapter)
        stats = await pipeline.run_cdc(adapter, since=last_run_at)
    """

    def __init__(
        self,
        store,
        embedder,
        embedder_id: str,
        audit_log: PiiAuditLog | None = None,
        chunker_configs: dict[str, ChunkerConfig] | None = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._embedder_id = embedder_id
        self._audit_log = audit_log or PiiAuditLog()
        self._configs = chunker_configs or CHUNKER_CONFIGS

    @property
    def audit_log(self) -> PiiAuditLog:
        return self._audit_log

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def ingest(self, adapter: SourceAdapter) -> dict:
        """Ingest (or re-ingest) all documents from the adapter.

        Returns a stats dict: {total, skipped, upserted, redactions}.
        """
        tracer = get_tracer("mcp_gateway.ingestion")
        with tracer.start_as_current_span("ingestion.full_scan") as span:
            stats = {"total": 0, "skipped": 0, "upserted": 0, "redactions": 0}
            async for doc in adapter.list_documents():
                doc_stats = await self._ingest_document(doc, tracer)
                _merge_stats(stats, doc_stats)
            span.set_attribute("ingestion.total", stats["total"])
            span.set_attribute("ingestion.upserted", stats["upserted"])
            span.set_attribute("ingestion.skipped", stats["skipped"])
            span.set_attribute("ingestion.redactions", stats["redactions"])
            logger.info({"event": "ingestion.full_scan.done", **stats})
            return stats

    async def run_cdc(self, adapter: SourceAdapter, since: datetime) -> dict:
        """Re-ingest only modified documents and tombstone deleted ones.

        Returns a stats dict: {total, skipped, upserted, deleted, redactions}.
        """
        tracer = get_tracer("mcp_gateway.ingestion")
        with tracer.start_as_current_span("ingestion.cdc") as span:
            span.set_attribute("ingestion.since", since.isoformat())
            stats = {"total": 0, "skipped": 0, "upserted": 0, "deleted": 0, "redactions": 0}

            # Modified documents
            async for doc in adapter.list_modified(since):
                doc_stats = await self._ingest_document(doc, tracer)
                _merge_stats(stats, doc_stats)

            # Deleted documents
            async for source_id in adapter.list_deleted_ids(since):
                with tracer.start_as_current_span("ingestion.delete_source") as del_span:
                    del_span.set_attribute("ingestion.source_id", source_id)
                    # We need to find which tenants had this source; the store
                    # exposes delete_by_source per tenant. For the in-memory
                    # store we pass tenant="" which triggers a global scan.
                    count = self._store.delete_by_source("", source_id) if hasattr(self._store, "delete_by_source") else 0
                    stats["deleted"] += count
                    del_span.set_attribute("ingestion.deleted_chunks", count)
                    logger.info({"event": "ingestion.source_deleted", "source_id": source_id, "chunks_removed": count})

            span.set_attribute("ingestion.total", stats["total"])
            span.set_attribute("ingestion.upserted", stats["upserted"])
            span.set_attribute("ingestion.deleted", stats["deleted"])
            logger.info({"event": "ingestion.cdc.done", **stats})
            return stats

    # ------------------------------------------------------------------
    # Per-document pipeline
    # ------------------------------------------------------------------

    async def _ingest_document(self, doc: SourceDocument, tracer) -> dict:
        stats = {"total": 0, "skipped": 0, "upserted": 0, "redactions": 0}

        # Stage 1: PII scrub
        with tracer.start_as_current_span("ingestion.pii_scrub") as span:
            span.set_attribute("ingestion.source_id", doc.source_id)
            scrub_result = scrub_pii(doc.text)
            scrubbed_doc = SourceDocument(
                source_id=doc.source_id,
                tenant=doc.tenant,
                text=scrub_result.text,
                acl=doc.acl,
                modified_at=doc.modified_at,
                extra=doc.extra,
            )
            redaction_count = sum(c for _, c in scrub_result.redactions)
            span.set_attribute("ingestion.redactions", redaction_count)
            stats["redactions"] += redaction_count

        # Write redactions to audit log
        if scrub_result.redactions:
            for pattern_type, count in scrub_result.redactions:
                self._audit_log.record(PiiAuditEntry(
                    source_id=doc.source_id,
                    chunk_ref=f"{doc.source_id}#pii_scrub",
                    pattern_type=pattern_type,
                    count=count,
                ))

        # Stage 2: Chunking
        with tracer.start_as_current_span("ingestion.chunk") as span:
            source_type = doc.extra.get("source_type", "default")
            config = self._configs.get(source_type, self._configs["default"])
            chunks = chunk_document(scrubbed_doc, embedder_id=self._embedder_id, config=config)
            span.set_attribute("ingestion.chunk_count", len(chunks))

        # Stage 3: Validate metadata and upsert (idempotent)
        with tracer.start_as_current_span("ingestion.embed_upsert") as span:
            upserted = 0
            skipped = 0
            for chunk in chunks:
                validate_chunk_metadata(chunk.metadata)
                content_hash = chunk.metadata["content_hash"]
                tenant = chunk.metadata["tenant"]

                # Idempotency check
                if hasattr(self._store, "chunk_exists") and self._store.chunk_exists(tenant, content_hash):
                    skipped += 1
                    continue

                # Embed
                with tracer.start_as_current_span("ingestion.embed"):
                    vector = self._embedder.embed(chunk.text)

                # Upsert
                with tracer.start_as_current_span("ingestion.upsert"):
                    if hasattr(self._store, "upsert"):
                        self._store.upsert(
                            owner_id=tenant,
                            text=chunk.text,
                            vector=vector,
                            chunk_id=content_hash,
                            source_id=doc.source_id,
                        )
                upserted += 1

            stats["total"] += len(chunks)
            stats["upserted"] += upserted
            stats["skipped"] += skipped
            span.set_attribute("ingestion.upserted", upserted)
            span.set_attribute("ingestion.skipped", skipped)

        logger.debug({
            "event": "ingestion.document_done",
            "source_id": doc.source_id,
            "tenant": doc.tenant,
            "chunks": len(chunks),
            "upserted": upserted,
            "skipped": skipped,
        })
        return stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_stats(target: dict, source: dict) -> None:
    for k, v in source.items():
        target[k] = target.get(k, 0) + v


# ---------------------------------------------------------------------------
# IngestionWorker — message-bus path (backward-compat)
# ---------------------------------------------------------------------------

class IngestionWorker:
    """Listens for agent output messages and ingests them into a vector store.

    Usage::

        worker = IngestionWorker(bus, store, embedder)
        task = asyncio.create_task(worker.start())
        # ... later
        task.cancel()
    """

    def __init__(self, bus, store, embedder, chunk_size: int = 512, overlap: int = 64) -> None:
        self._bus = bus
        self._store = store
        self._embedder = embedder
        self._chunk_size = chunk_size
        self._overlap = overlap
        self._queue = bus.subscribe("agent.output.final")

    async def start(self) -> None:
        try:
            while True:
                msg = await self._queue.get()
                await self._process(msg)
        except asyncio.CancelledError:
            pass

    async def _process(self, msg) -> None:
        text: str = msg.content["text"]
        owner_id: str = msg.content["owner_id"]
        source: str = msg.content.get("source", "")

        chunks = chunk_text(text, source=source, chunk_size=self._chunk_size, overlap=self._overlap)
        for chunk in chunks:
            self._store.upsert(owner_id, chunk.text, self._embedder.embed(chunk.text))

        logger.debug({
            "event": "ingest_processed",
            "owner_id": owner_id,
            "chunk_count": len(chunks),
            "chunk_size": self._chunk_size,
            "overlap": self._overlap,
        })
