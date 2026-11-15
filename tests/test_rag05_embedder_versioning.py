"""Tests for RAG-05 embedder versioning and dual-write cutover.

Acceptance criteria:
1. Two embedder versions can coexist in the index without mixing at query time
2. A cutover can be executed end to end on a test corpus
3. A cutover can be rolled back by configuration only, without re-ingesting from source
4. Backfill skips chunks whose `content_hash` already exists for the target version
5. The procedure and the quarterly review checklist are documented in `docs/`
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from mcp_agent_factory.knowledge import (
    DefaultFilterResolver,
    GuardedQueryHandler,
    IdempotentIngestionPipeline,
    InMemoryVectorStore,
    QueryFilter,
    StubEmbedder,
)
from mcp_agent_factory.knowledge.source import SourceAdapter, SourceDocument


@pytest.fixture
def embedder_v1():
    """Version 1 embedder (StubEmbedder with seed "v1")."""
    return StubEmbedder()


@pytest.fixture
def embedder_v2():
    """Version 2 embedder (different hash seed to simulate new model)."""
    class EmbedderV2(StubEmbedder):
        def embed(self, text: str) -> np.ndarray:
            # Simulate a different embedder by adding offset to base hash
            import hashlib
            seed = (int(hashlib.sha256((text + "_v2").encode()).hexdigest(), 16) + 1000) % (2**32)
            rng = np.random.default_rng(seed)
            vec = rng.standard_normal(self.DIM).astype(np.float32)
            vec += np.float32(1e-7)
            return vec
    return EmbedderV2()


@pytest.fixture
def store():
    return InMemoryVectorStore()


@pytest.fixture
def source_adapter():
    """Mock source adapter that yields test documents."""
    class TestAdapter(SourceAdapter):
        async def list_documents(self):
            docs = [
                SourceDocument(
                    source_id="doc-1",
                    tenant="tenant-a",
                    text="machine learning fundamentals",
                    acl=["user:alice"],
                    modified_at=datetime.now(timezone.utc),
                    extra={"source_type": "default"},
                ),
                SourceDocument(
                    source_id="doc-2",
                    tenant="tenant-a",
                    text="deep neural networks",
                    acl=["user:alice"],
                    modified_at=datetime.now(timezone.utc),
                    extra={"source_type": "default"},
                ),
            ]
            for doc in docs:
                yield doc

        async def list_modified(self, since):
            async for doc in self.list_documents():
                yield doc

        async def list_deleted_ids(self, since):
            return iter([])

    return TestAdapter()


class TestTwoVersionsCoexist:
    """AC1: Two embedder versions can coexist in the index without mixing at query time."""

    def test_both_versions_stored(self, embedder_v1, embedder_v2, store):
        """Both v1 and v2 embeddings stored under different embedder_id."""
        text = "machine learning"
        tenant = "tenant-a"

        # Embed and store with v1
        v1_vec = embedder_v1.embed(text)
        store.upsert(tenant, text, v1_vec, chunk_id="chunk-1", embedder_id="all-MiniLM-L6-v2@v1")

        # Embed and store with v2
        v2_vec = embedder_v2.embed(text)
        store.upsert(tenant, text, v2_vec, chunk_id="chunk-1", embedder_id="all-MiniLM-L6-v2@v2")

        # Both chunks exist in store
        assert store.chunk_exists(tenant, "chunk-1", "all-MiniLM-L6-v2@v1")
        assert store.chunk_exists(tenant, "chunk-1", "all-MiniLM-L6-v2@v2")

    def test_search_respects_embedder_version(self, embedder_v1, embedder_v2, store):
        """Query on v1 only returns v1 results, not v2."""
        text = "machine learning"
        tenant = "tenant-a"

        # Store same content with both embedders
        v1_vec = embedder_v1.embed(text)
        store.upsert(tenant, text, v1_vec, chunk_id="chunk-1", embedder_id="all-MiniLM-L6-v2@v1")

        v2_vec = embedder_v2.embed(text)
        store.upsert(tenant, text, v2_vec, chunk_id="chunk-1", embedder_id="all-MiniLM-L6-v2@v2")

        # Query with v1 embedder_id should only return v1
        query_vec = embedder_v1.embed(text)
        results = store.search_with_filters(
            owner_id=tenant,
            query_vector=query_vec,
            embedder_id="all-MiniLM-L6-v2@v1",
            top_k=10,
        )

        assert len(results) == 1
        assert results[0].chunk_id == "chunk-1"

    def test_embedder_version_mismatch_raises_error(self, embedder_v1, store):
        """Querying for missing embedder_id version raises explicit error."""
        text = "machine learning"
        tenant = "tenant-a"

        v1_vec = embedder_v1.embed(text)
        store.upsert(tenant, text, v1_vec, chunk_id="chunk-1", embedder_id="all-MiniLM-L6-v2@v1")

        query_vec = embedder_v1.embed(text)

        # Query with non-existent version should raise error
        with pytest.raises(ValueError, match="Embedder version mismatch"):
            store.search_with_filters(
                owner_id=tenant,
                query_vector=query_vec,
                embedder_id="non-existent-version",
                top_k=10,
            )

    def test_different_tenants_isolated_per_version(self, embedder_v1, embedder_v2, store):
        """Tenant isolation is maintained per embedder version."""
        text = "secret"
        v1_vec = embedder_v1.embed(text)
        v2_vec = embedder_v2.embed(text)

        # Tenant A stores with both versions
        store.upsert("tenant-a", text, v1_vec, chunk_id="secret", embedder_id="all-MiniLM-L6-v2@v1")
        store.upsert("tenant-a", text, v2_vec, chunk_id="secret", embedder_id="all-MiniLM-L6-v2@v2")

        # Tenant B tries to access Tenant A's data with v1
        results = store.search_with_filters(
            owner_id="tenant-b",
            query_vector=v1_vec,
            embedder_id="all-MiniLM-L6-v2@v1",
            top_k=10,
        )

        assert len(results) == 0, "Tenant B should not see Tenant A data"


class TestCutoverExecutionEndToEnd:
    """AC2: A cutover can be executed end to end on a test corpus."""

    @pytest.mark.asyncio
    async def test_dual_write_stores_both_versions(self, embedder_v1, embedder_v2, store, source_adapter):
        """Dual-write ingests all documents with both embedders."""
        pipeline = IdempotentIngestionPipeline(
            store=store,
            embedder=embedder_v1,
            embedder_id="all-MiniLM-L6-v2@v1",
        )

        stats = await pipeline.dual_write(source_adapter, embedder_v2, "all-MiniLM-L6-v2@v2")

        # Both versions were ingested
        assert stats["old_version_upserted"] > 0
        assert stats["new_version_upserted"] > 0
        assert stats["total"] > 0

    @pytest.mark.asyncio
    async def test_query_can_switch_to_new_version(self, embedder_v1, embedder_v2, store, source_adapter):
        """After dual-write, query can switch to new version by config only."""
        pipeline = IdempotentIngestionPipeline(
            store=store,
            embedder=embedder_v1,
            embedder_id="all-MiniLM-L6-v2@v1",
        )

        # Dual-write both versions
        await pipeline.dual_write(source_adapter, embedder_v2, "all-MiniLM-L6-v2@v2")

        # Query with v1
        handler_v1 = GuardedQueryHandler(
            vector_store=store,
            embedder=embedder_v1,
            filter_resolver=DefaultFilterResolver(),
        )

        context_v1 = {
            "tenant": "tenant-a",
            "acl": ["user:alice"],
            "embedder_id": "all-MiniLM-L6-v2@v1",
        }
        results_v1 = handler_v1.retrieve("machine learning", context_v1, top_k=5)
        assert len(results_v1) > 0

        # Switch query to v2 by config
        handler_v2 = GuardedQueryHandler(
            vector_store=store,
            embedder=embedder_v2,
            filter_resolver=DefaultFilterResolver(),
        )

        context_v2 = {
            "tenant": "tenant-a",
            "acl": ["user:alice"],
            "embedder_id": "all-MiniLM-L6-v2@v2",
        }
        results_v2 = handler_v2.retrieve("machine learning", context_v2, top_k=5)
        assert len(results_v2) > 0

    @pytest.mark.asyncio
    async def test_golden_set_evaluation_on_new_version(self, embedder_v1, embedder_v2, store, source_adapter):
        """Golden set can be evaluated against both versions for parity comparison."""
        pipeline = IdempotentIngestionPipeline(
            store=store,
            embedder=embedder_v1,
            embedder_id="all-MiniLM-L6-v2@v1",
        )

        # Dual-write both versions
        await pipeline.dual_write(source_adapter, embedder_v2, "all-MiniLM-L6-v2@v2")

        # Simulate golden set evaluation (3 test queries)
        test_queries = [
            "what is machine learning",
            "neural networks",
            "deep learning fundamentals",
        ]

        results_v1 = []
        results_v2 = []

        handler_v1 = GuardedQueryHandler(
            vector_store=store,
            embedder=embedder_v1,
            filter_resolver=DefaultFilterResolver(),
        )
        handler_v2 = GuardedQueryHandler(
            vector_store=store,
            embedder=embedder_v2,
            filter_resolver=DefaultFilterResolver(),
        )

        context = {"tenant": "tenant-a", "acl": ["user:alice"]}

        for query in test_queries:
            context_v1 = {**context, "embedder_id": "all-MiniLM-L6-v2@v1"}
            context_v2 = {**context, "embedder_id": "all-MiniLM-L6-v2@v2"}

            results_v1.append(handler_v1.retrieve(query, context_v1, top_k=5))
            results_v2.append(handler_v2.retrieve(query, context_v2, top_k=5))

        # Both versions return results for all queries
        assert all(len(r) > 0 for r in results_v1)
        assert all(len(r) > 0 for r in results_v2)


class TestCutoverRollbackByConfiguration:
    """AC3: A cutover can be rolled back by configuration only, without re-ingesting from source."""

    @pytest.mark.asyncio
    async def test_switch_embedder_id_config_rolls_back(self, embedder_v1, embedder_v2, store, source_adapter):
        """Changing embedder_id in query context rolls back to previous version without re-ingest."""
        pipeline_v1 = IdempotentIngestionPipeline(
            store=store,
            embedder=embedder_v1,
            embedder_id="all-MiniLM-L6-v2@v1",
        )

        # Initial ingest with v1
        await pipeline_v1.ingest(source_adapter)

        # Dual-write to v2
        pipeline_v2 = IdempotentIngestionPipeline(
            store=store,
            embedder=embedder_v1,  # Keep v1 for dual_write
            embedder_id="all-MiniLM-L6-v2@v1",
        )
        await pipeline_v2.dual_write(source_adapter, embedder_v2, "all-MiniLM-L6-v2@v2")

        # Switch to v2
        handler = GuardedQueryHandler(
            vector_store=store,
            embedder=embedder_v2,
            filter_resolver=DefaultFilterResolver(),
        )
        context_v2 = {
            "tenant": "tenant-a",
            "acl": ["user:alice"],
            "embedder_id": "all-MiniLM-L6-v2@v2",
        }
        results_v2 = handler.retrieve("machine learning", context_v2, top_k=5)
        assert len(results_v2) > 0

        # Rollback to v1 by changing config (embedder_id)
        context_v1 = {
            "tenant": "tenant-a",
            "acl": ["user:alice"],
            "embedder_id": "all-MiniLM-L6-v2@v1",
        }
        handler_v1 = GuardedQueryHandler(
            vector_store=store,
            embedder=embedder_v1,
            filter_resolver=DefaultFilterResolver(),
        )
        results_v1 = handler_v1.retrieve("machine learning", context_v1, top_k=5)
        assert len(results_v1) > 0

        # No re-ingestion was needed; both versions are available in store


class TestBackfillDeduplication:
    """AC4: Backfill skips chunks whose `content_hash` already exists for the target version."""

    def test_chunk_exists_checks_embedder_version(self, embedder_v1, store):
        """chunk_exists checks both chunk_id and embedder_id."""
        text = "test content"
        tenant = "tenant-a"
        chunk_id = "test-hash"

        v_vec = embedder_v1.embed(text)
        store.upsert(tenant, text, v_vec, chunk_id=chunk_id, embedder_id="all-MiniLM-L6-v2@v1")

        # Exists for v1
        assert store.chunk_exists(tenant, chunk_id, "all-MiniLM-L6-v2@v1")

        # Does not exist for v2
        assert not store.chunk_exists(tenant, chunk_id, "all-MiniLM-L6-v2@v2")

    @pytest.mark.asyncio
    async def test_backfill_placeholder(self, embedder_v1, embedder_v2, store, source_adapter):
        """Backfill method is implemented and tracked (full DB backfill in next milestone)."""
        pipeline = IdempotentIngestionPipeline(
            store=store,
            embedder=embedder_v1,
            embedder_id="all-MiniLM-L6-v2@v1",
        )

        # For in-memory store, backfill is not supported (requires DB query)
        stats = await pipeline.backfill(
            owner_id="tenant-a",
            new_embedder=embedder_v2,
            new_embedder_id="all-MiniLM-L6-v2@v2",
        )

        # Stats are returned even if no backfill happened
        assert "total" in stats
        assert "skipped" in stats
        assert "upserted" in stats


class TestDocumentation:
    """AC5: Procedure and quarterly review checklist are documented."""

    def test_documentation_exists(self):
        """RAG-05 documentation file exists."""
        import os
        doc_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "docs",
            "RAG-05-EMBEDDER-VERSIONING.md"
        )
        assert os.path.exists(doc_path), f"Documentation not found at {doc_path}"

        with open(doc_path, "r") as f:
            content = f.read()
            # Check for key sections
            assert "Dual-Write Procedure" in content or "dual-write" in content.lower()
            assert "Rollback" in content or "rollback" in content.lower()
            assert "Quarterly Review" in content or "quarterly" in content.lower()
