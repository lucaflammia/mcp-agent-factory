"""Additional patch-coverage tests for RAG-07 diff lines.

Covers uncovered new lines in:
- source.py (FileSourceAdapter, InMemorySourceAdapter)
- vector_store.py (InMemoryVectorStore async helpers, restore-from-dict, search_text_with_source)
- reranker.py (empty candidates, CrossEncoderReranker)
- gateway/app.py (query endpoint)
- pii.py (PiiAuditLog.entries)
- tools.py (exception StatusCode fallback)
- embedder.py (LocalEmbedder lazy load)
"""
import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# source.py — FileSourceAdapter
# ---------------------------------------------------------------------------

class TestFileSourceAdapter:
    def test_read_plain_text_file(self, tmp_path):
        from mcp_agent_factory.knowledge.source import FileSourceAdapter

        f = tmp_path / "doc.txt"
        f.write_text("hello world")
        adapter = FileSourceAdapter(path=str(f), tenant="t1")
        docs = asyncio.run(
            _collect_async(adapter.list_documents())
        )
        assert len(docs) == 1
        assert docs[0].text == "hello world"
        assert docs[0].tenant == "t1"
        assert docs[0].extra["source_type"] == "default"

    def test_read_pdf_fallback_to_text(self, tmp_path, monkeypatch):
        import sys

        from mcp_agent_factory.knowledge.source import FileSourceAdapter

        # Force both PDF libraries to be unavailable so the plain-text fallback runs
        monkeypatch.setitem(sys.modules, "fitz", None)
        monkeypatch.setitem(sys.modules, "pypdf", None)

        f = tmp_path / "doc.pdf"
        f.write_text("not-really-a-pdf")
        adapter = FileSourceAdapter(path=str(f), tenant="t1")
        docs = asyncio.run(
            _collect_async(adapter.list_documents())
        )
        assert len(docs) == 1
        assert docs[0].extra["source_type"] == "pdf"
        assert "not-really-a-pdf" in docs[0].text

    def test_read_pdf_with_pypdf(self, tmp_path, monkeypatch):
        import sys

        from mcp_agent_factory.knowledge.source import FileSourceAdapter

        # Hide fitz so pypdf path is taken
        monkeypatch.setitem(sys.modules, "fitz", None)

        # Create a minimal valid PDF
        f = tmp_path / "test.pdf"
        try:
            from pypdf import PdfWriter
            writer = PdfWriter()
            from pypdf._page import PageObject
            page = PageObject.create_blank_page(width=72, height=72)
            writer.add_page(page)
            with open(f, "wb") as fh:
                writer.write(fh)
        except ImportError:
            pytest.skip("pypdf not installed")

        adapter = FileSourceAdapter(path=str(f), tenant="t1")
        docs = asyncio.run(
            _collect_async(adapter.list_documents())
        )
        assert len(docs) == 1
        assert docs[0].extra["source_type"] == "pdf"

    def test_source_id_defaults_to_path(self, tmp_path):
        from mcp_agent_factory.knowledge.source import FileSourceAdapter

        f = tmp_path / "doc.txt"
        f.write_text("x")
        adapter = FileSourceAdapter(path=str(f), tenant="t1")
        assert adapter._source_id == str(f)

    def test_source_id_override(self, tmp_path):
        from mcp_agent_factory.knowledge.source import FileSourceAdapter

        f = tmp_path / "doc.txt"
        f.write_text("x")
        adapter = FileSourceAdapter(path=str(f), tenant="t1", source_id="custom")
        assert adapter._source_id == "custom"

    def test_list_modified_recent(self, tmp_path):
        from mcp_agent_factory.knowledge.source import FileSourceAdapter

        f = tmp_path / "doc.txt"
        f.write_text("hello")
        since = datetime(2000, 1, 1, tzinfo=timezone.utc)
        adapter = FileSourceAdapter(path=str(f), tenant="t1")
        docs = asyncio.run(
            _collect_async(adapter.list_modified(since))
        )
        assert len(docs) == 1

    def test_list_modified_old(self, tmp_path):
        from mcp_agent_factory.knowledge.source import FileSourceAdapter

        f = tmp_path / "doc.txt"
        f.write_text("hello")
        since = datetime(2099, 1, 1, tzinfo=timezone.utc)
        adapter = FileSourceAdapter(path=str(f), tenant="t1")
        docs = asyncio.run(
            _collect_async(adapter.list_modified(since))
        )
        assert len(docs) == 0

    def test_list_deleted_ids_empty(self, tmp_path):
        from mcp_agent_factory.knowledge.source import FileSourceAdapter

        f = tmp_path / "doc.txt"
        f.write_text("hello")
        adapter = FileSourceAdapter(path=str(f), tenant="t1")
        since = datetime(2000, 1, 1, tzinfo=timezone.utc)
        ids = asyncio.run(
            _collect_async(adapter.list_deleted_ids(since))
        )
        assert ids == []


class TestInMemorySourceAdapter:
    def test_list_documents(self):
        from mcp_agent_factory.knowledge.source import InMemorySourceAdapter, SourceDocument

        doc = SourceDocument(source_id="s1", tenant="t1", text="hello")
        adapter = InMemorySourceAdapter([doc])
        docs = asyncio.run(
            _collect_async(adapter.list_documents())
        )
        assert len(docs) == 1

    def test_add_and_delete(self):
        from mcp_agent_factory.knowledge.source import InMemorySourceAdapter, SourceDocument

        adapter = InMemorySourceAdapter()
        doc = SourceDocument(source_id="s1", tenant="t1", text="hello")
        adapter.add(doc)
        adapter.delete("s1")
        docs = asyncio.run(
            _collect_async(adapter.list_documents())
        )
        assert len(docs) == 0

    def test_list_deleted_ids(self):
        from mcp_agent_factory.knowledge.source import InMemorySourceAdapter, SourceDocument

        adapter = InMemorySourceAdapter()
        doc = SourceDocument(source_id="s1", tenant="t1", text="hello")
        adapter.add(doc)
        adapter.delete("s1")
        since = datetime(2000, 1, 1, tzinfo=timezone.utc)
        ids = asyncio.run(
            _collect_async(adapter.list_deleted_ids(since))
        )
        assert "s1" in ids


# ---------------------------------------------------------------------------
# vector_store.py — InMemoryVectorStore async helpers & restore-from-dict
# ---------------------------------------------------------------------------

class TestInMemoryVectorStoreAsyncHelpers:
    def test_delete_by_source_id_async(self):
        from mcp_agent_factory.knowledge.vector_store import InMemoryVectorStore

        store = InMemoryVectorStore()
        store.upsert("owner", "text1", np.array([1.0, 0.0]), chunk_id="c1", source_id="src1")
        count = asyncio.run(
            store.delete_by_source_id("src1", "owner")
        )
        assert count == 1

    def test_delete_by_data_subject_id_async(self):
        from mcp_agent_factory.knowledge.vector_store import InMemoryVectorStore

        store = InMemoryVectorStore()
        store.upsert("owner", "user@example.com data", np.array([1.0, 0.0]),
                      chunk_id="c1", source_id="user@example.com")
        count = asyncio.run(
            store.delete_by_data_subject_id("user@example.com", "owner")
        )
        assert count == 1

    def test_restore_from_dict(self, tmp_path):
        from mcp_agent_factory.knowledge.vector_store import InMemoryVectorStore

        store = InMemoryVectorStore()
        store.upsert("o", "txt", np.array([1.0, 2.0]), chunk_id="c1", source_id="s1")
        backup_meta = store.backup(str(tmp_path / "backup.json"))
        store2 = InMemoryVectorStore()
        result = store2.restore(backup_meta)
        assert result["chunks_restored"] == 1

    def test_restore_from_dict_missing_key(self):
        from mcp_agent_factory.knowledge.vector_store import InMemoryVectorStore

        store = InMemoryVectorStore()
        with pytest.raises(ValueError, match="backup_path"):
            store.restore({})

    def test_search_text_with_source(self):
        from mcp_agent_factory.knowledge.vector_store import InMemoryVectorStore

        store = InMemoryVectorStore()
        store.upsert("o", "quarterly revenue report", np.array([1.0, 0.0]),
                      chunk_id="c1", source_id="finance.pdf")
        store.upsert("o", "quarterly expense summary", np.array([0.0, 1.0]),
                      chunk_id="c2", source_id="other.pdf")
        results = store.search_text_with_source("o", "quarterly", "finance.pdf")
        assert len(results) == 1
        assert "revenue" in results[0][0]

    def test_search_with_filters_source_id(self):
        from mcp_agent_factory.knowledge.vector_store import InMemoryVectorStore

        store = InMemoryVectorStore()
        store.upsert("o", "text1", np.array([1.0, 0.0]), chunk_id="c1",
                      source_id="s1", embedder_id="e1")
        store.upsert("o", "text2", np.array([0.0, 1.0]), chunk_id="c2",
                      source_id="s2", embedder_id="e1")
        results = store.search_with_filters("o", np.array([1.0, 0.0]), top_k=5,
                                            source_id="s1")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# reranker.py — empty candidates + CrossEncoderReranker
# ---------------------------------------------------------------------------

class TestRerankerEdgeCases:
    def test_mmr_diversify_empty_candidates(self):
        from mcp_agent_factory.knowledge.reranker import mmr_diversify

        result = mmr_diversify([], {})
        assert result == []

    def test_cross_encoder_reranker_disabled(self):
        from mcp_agent_factory.knowledge.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker(enabled=False)
        candidates = [("a", 0.9), ("b", 0.8)]
        result = reranker.rerank("query", candidates, top_k=1)
        assert len(result) == 1

    def test_cross_encoder_reranker_load_and_rerank(self):
        import sys

        from mcp_agent_factory.knowledge.reranker import CrossEncoderReranker

        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0.5, 0.9])

        mock_st = MagicMock()
        mock_st.CrossEncoder.return_value = mock_model

        with patch.dict(sys.modules, {"sentence_transformers": mock_st}):
            reranker = CrossEncoderReranker(enabled=True)
            candidates = [("a", 0.1), ("b", 0.2)]
            result = reranker.rerank("query", candidates, top_k=2)
            assert result[0][0] == "b"
            mock_st.CrossEncoder.assert_called_once()


# ---------------------------------------------------------------------------
# gateway/app.py — query endpoint
# ---------------------------------------------------------------------------

class TestQueryEndpoint:
    def test_query_endpoint_no_vector_store(self):
        from fastapi.testclient import TestClient

        import mcp_agent_factory.gateway.app as app_mod

        old_vs = app_mod._vector_store
        old_emb = app_mod._embedder
        try:
            app_mod._vector_store = None
            app_mod._embedder = None
            client = TestClient(app_mod.gateway_app, raise_server_exceptions=False)
            resp = client.post("/query", json={"question": "q", "tenant": "t"})
            assert resp.status_code == 503
        finally:
            app_mod._vector_store = old_vs
            app_mod._embedder = old_emb

    def test_query_endpoint_with_store(self):
        from fastapi.testclient import TestClient

        import mcp_agent_factory.gateway.app as app_mod
        from mcp_agent_factory.knowledge.vector_store import InMemoryVectorStore

        store = InMemoryVectorStore()
        store.upsert("t", "Net income was $8.1M in Q3", np.array([1.0, 0.0, 0.0]),
                      chunk_id="c1", source_id="report.pdf")

        class FakeEmbedder:
            def embed(self, text):
                return np.array([1.0, 0.0, 0.0])

        import fakeredis.aioredis as _fakeredis
        from mcp_agent_factory.gateway.query_management import QueryManager, RateLimitConfig
        from mcp_agent_factory.kv.store import RedisKVStore

        old_vs = app_mod._vector_store
        old_emb = app_mod._embedder
        old_qm = app_mod._query_manager
        try:
            app_mod._vector_store = store
            app_mod._embedder = FakeEmbedder()
            # Fresh fakeredis + QueryManager so the new TestClient's event loop
            # doesn't reuse a Redis connection bound to a previous (closed) loop.
            fresh_redis = _fakeredis.FakeRedis()
            app_mod._query_manager = QueryManager(
                kv_store=RedisKVStore(fresh_redis, topics=[]),
                redis_client=fresh_redis,
                config=RateLimitConfig(),
            )
            client = TestClient(app_mod.gateway_app, raise_server_exceptions=False)
            resp = client.post("/query", json={"question": "net income", "tenant": "t"})
            assert resp.status_code == 200
            data = resp.json()
            assert "answer" in data
        finally:
            app_mod._vector_store = old_vs
            app_mod._embedder = old_emb
            app_mod._query_manager = old_qm


# ---------------------------------------------------------------------------
# pii.py — PiiAuditLog.entries()
# ---------------------------------------------------------------------------

class TestPiiAuditLogEntries:
    def test_entries_returns_copy(self):
        from mcp_agent_factory.knowledge.pii import PiiAuditEntry, PiiAuditLog

        log = PiiAuditLog()
        entry = PiiAuditEntry(source_id="s1", chunk_ref="c1", pattern_type="email", count=1)
        log.record(entry)
        entries = log.entries()
        assert len(entries) == 1
        entries.clear()
        assert len(log.entries()) == 1


# ---------------------------------------------------------------------------
# tools.py — exception path with ImportError on StatusCode
# ---------------------------------------------------------------------------

class TestToolsExceptionStatusCodeFallback:
    def test_query_exception_with_statuscode_import_error(self):
        from mcp_agent_factory.knowledge.tools import query_knowledge_base

        class FakeStore:
            def search(self, *a, **kw):
                raise RuntimeError("DB down")

        class FakeEmbedder:
            def embed(self, text):
                return np.array([1.0])

        with pytest.raises(RuntimeError, match="DB down"):
            query_knowledge_base("q", "owner", FakeStore(), FakeEmbedder())


# ---------------------------------------------------------------------------
# embedder.py — LocalEmbedder lazy load
# ---------------------------------------------------------------------------

class TestLocalEmbedderLazyLoad:
    def test_lazy_load_import_error(self):
        from mcp_agent_factory.knowledge.embedder import LocalEmbedder

        embedder = LocalEmbedder()
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            with pytest.raises((ImportError, ModuleNotFoundError)):
                embedder._model = None
                embedder._load()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _collect_async(ait):
    result = []
    async for item in ait:
        result.append(item)
    return result
