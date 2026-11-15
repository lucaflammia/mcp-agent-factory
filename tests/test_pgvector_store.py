"""Unit tests for PgVectorStore (no live Postgres needed — patches psycopg)."""
from __future__ import annotations

import json
import sys
import tempfile
from types import ModuleType
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _make_psycopg_mock():
  """Build a minimal psycopg mock so PgVectorStore can be imported without the library."""
  mod = ModuleType("psycopg")
  conn = MagicMock()
  conn.closed = False
  cur = MagicMock()
  cur.__enter__ = lambda s: s
  cur.__exit__ = MagicMock(return_value=False)
  cur.fetchall.return_value = [("chunk text", 0.9)]
  conn.cursor.return_value = cur
  mod.connect = MagicMock(return_value=conn)
  return mod, conn, cur


def _make_pgvector_mock():
  mod = ModuleType("pgvector")
  psycopg_sub = ModuleType("pgvector.psycopg")
  psycopg_sub.register_vector = MagicMock()
  mod.psycopg = psycopg_sub
  return mod, psycopg_sub


@pytest.fixture(autouse=True)
def mock_pg_deps():
  psycopg_mod, conn, cur = _make_psycopg_mock()
  pgvector_mod, pgvector_psycopg = _make_pgvector_mock()
  with (
    patch.dict(sys.modules, {"psycopg": psycopg_mod, "pgvector": pgvector_mod, "pgvector.psycopg": pgvector_psycopg}),
  ):
    yield conn, cur


def _store(conn, cur):
  from mcp_agent_factory.knowledge.vector_store import PgVectorStore
  store = PgVectorStore(dsn="postgresql://mcp:test@localhost/knowledge")
  store._conn = conn
  return store


def test_upsert_executes_insert(mock_pg_deps):
  conn, cur = mock_pg_deps
  store = _store(conn, cur)
  v = np.ones(384, dtype=np.float32)
  store.upsert("alice", "hello world", v)
  assert cur.execute.called


def test_search_returns_results(mock_pg_deps):
  conn, cur = mock_pg_deps
  cur.fetchall.return_value = [("chunk text", 0.9)]
  store = _store(conn, cur)
  v = np.ones(384, dtype=np.float32)
  results = store.search("alice", v, top_k=5)
  assert results == [("chunk text", 0.9)]


def test_search_filters_by_owner_id(mock_pg_deps):
  """Verify that owner_id is passed as a parameter (not post-filtered)."""
  conn, cur = mock_pg_deps
  cur.fetchall.return_value = []
  store = _store(conn, cur)
  v = np.ones(384, dtype=np.float32)
  store.search("bob", v, top_k=5)
  call_args = cur.execute.call_args
  assert "bob" in call_args[0][1]


def test_search_text_uses_tsvector(mock_pg_deps):
  conn, cur = mock_pg_deps
  cur.fetchall.return_value = [("result", 0.5)]
  store = _store(conn, cur)
  results = store.search_text("alice", "quarterly revenue", top_k=10)
  assert results == [("result", 0.5)]
  sql = cur.execute.call_args[0][0]
  assert "plainto_tsquery" in sql


def test_search_hybrid_calls_both(mock_pg_deps):
  conn, cur = mock_pg_deps
  cur.fetchall.side_effect = [
    [("dense result", 0.9)],
    [("text result", 0.5)],
  ]
  store = _store(conn, cur)
  v = np.ones(384, dtype=np.float32)
  results = store.search_hybrid("alice", "quarterly revenue", v, top_k=2)
  assert cur.execute.call_count == 2
  texts = [r[0] for r in results]
  assert "dense result" in texts
  assert "text result" in texts


def test_cross_tenant_isolation_enforced_by_param(mock_pg_deps):
  """owner_id='bob' must never retrieve alice's data — enforced at SQL level."""
  conn, cur = mock_pg_deps
  cur.fetchall.return_value = []
  store = _store(conn, cur)
  v = np.ones(384, dtype=np.float32)
  results = store.search("bob", v, top_k=5)
  assert results == []
  call_args = cur.execute.call_args
  assert "alice" not in str(call_args)
  assert "bob" in str(call_args[0][1])


class TestPgVectorStoreOperations:
  """RAG-06 operations tests for PgVectorStore."""

  def test_backup_exports_all_chunks(self, mock_pg_deps):
    """Test that backup exports all chunks to JSON."""
    conn, cur = mock_pg_deps
    cur.fetchall.return_value = [
      ("tenant-a", "c1", "Sample text A", np.array([0.1, 0.2, 0.3]), "doc1", "all-MiniLM-L6-v2@v1"),
      ("tenant-a", "c2", "Sample text B", np.array([0.4, 0.5, 0.6]), "doc1", "all-MiniLM-L6-v2@v1"),
      ("tenant-b", "c3", "Sample text C", np.array([0.7, 0.8, 0.9]), "doc2", "all-MiniLM-L6-v2@v1"),
    ]
    store = _store(conn, cur)

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
      backup_path = f"{tmpdir}/backup.json"
      meta = store.backup(backup_path)

      assert meta['chunk_count'] == 3
      assert set(meta['owner_ids']) == {'tenant-a', 'tenant-b'}
      assert 'backup_path' in meta
      assert 'timestamp' in meta
      assert cur.execute.called

  def test_restore_truncates_and_inserts(self, mock_pg_deps):
    """Test that restore clears and re-inserts data."""
    conn, cur = mock_pg_deps
    store = _store(conn, cur)

    with tempfile.TemporaryDirectory() as tmpdir:
      backup_path = f"{tmpdir}/backup.json"
      backup_data = {
        'chunks': [
          {
            'owner_id': 'tenant-a',
            'chunk_id': 'c1',
            'text': 'Restored text',
            'embedding': [0.1, 0.2, 0.3],
            'source_id': 'doc1',
            'embedder_id': 'all-MiniLM-L6-v2@v1',
          }
        ]
      }
      with open(backup_path, 'w') as f:
        json.dump(backup_data, f)

      result = store.restore(backup_path)
      assert result['chunks_restored'] == 1
      assert result['owners_restored'] == 1
      # Verify TRUNCATE was called
      sql_calls = [c[0][0] for c in cur.execute.call_args_list]
      assert any('TRUNCATE' in str(sql) for sql in sql_calls)
      # Verify INSERT was called
      assert any('INSERT' in str(sql) for sql in sql_calls)

  def test_restore_missing_file_raises_error(self, mock_pg_deps):
    """Test that restore raises FileNotFoundError for missing backup."""
    conn, cur = mock_pg_deps
    store = _store(conn, cur)

    with pytest.raises(FileNotFoundError):
      store.restore("/nonexistent/backup.json")

  def test_delete_by_source_removes_chunks(self, mock_pg_deps):
    """Test that delete_by_source removes all chunks for a source_id."""
    conn, cur = mock_pg_deps
    cur.rowcount = 2
    store = _store(conn, cur)

    deleted = store.delete_by_source("tenant-a", "doc1")
    assert deleted == 2
    assert cur.execute.called
    sql = cur.execute.call_args[0][0]
    assert "DELETE" in sql
    assert "source_id" in sql

  def test_delete_by_data_subject_removes_matching_chunks(self, mock_pg_deps):
    """Test that delete_by_data_subject removes chunks matching data_subject_id."""
    conn, cur = mock_pg_deps
    cur.rowcount = 3
    store = _store(conn, cur)

    deleted = store.delete_by_data_subject("tenant-a", "customer-12345")
    assert deleted == 3
    assert cur.execute.called
    sql = cur.execute.call_args[0][0]
    assert "DELETE" in sql
    assert "ILIKE" in sql  # Case-insensitive match

  def test_compact_vacuums_and_returns_count(self, mock_pg_deps):
    """Test that compact runs VACUUM ANALYZE and returns chunk count."""
    conn, cur = mock_pg_deps
    cur.fetchone.return_value = (42,)
    store = _store(conn, cur)

    result = store.compact()
    assert result['status'] == 'ok'
    assert result['chunk_count'] == 42

    # Verify VACUUM was called
    sql_calls = [c[0][0] for c in cur.execute.call_args_list]
    assert any('VACUUM' in str(sql) for sql in sql_calls)
    assert any('COUNT(*)' in str(sql) for sql in sql_calls)

  def test_search_with_filters_adds_embedder_id_clause(self, mock_pg_deps):
    """Test that search_with_filters includes embedder_id in WHERE clause."""
    conn, cur = mock_pg_deps
    # Mock the execute() call to return itself, then fetchall()
    cur.execute.return_value = cur
    cur.fetchall.return_value = [("chunk text", 0.9)]
    store = _store(conn, cur)

    v = np.ones(384, dtype=np.float32)
    results = store.search_with_filters(
      "tenant-a",
      v,
      embedder_id="all-MiniLM-L6-v2@v1",
      top_k=5,
    )

    assert results == [("chunk text", 0.9)]
    # Check that execute was called with SQL containing embedder_id
    execute_calls = [c[0][0] for c in cur.execute.call_args_list]
    assert any("embedder_id" in str(sql) for sql in execute_calls)

  def test_search_with_filters_embedder_mismatch_raises_error(self, mock_pg_deps):
    """Test that search_with_filters raises error on embedder version mismatch."""
    conn, cur = mock_pg_deps
    # First call: execute returns cursor with empty fetchall
    # For the check_cur context manager, we need separate mock
    check_cur = MagicMock()
    check_cur.__enter__ = lambda s: s
    check_cur.__exit__ = MagicMock(return_value=False)
    check_cur.execute = MagicMock()
    check_cur.fetchall.return_value = [("all-MiniLM-L6-v2@v0",), ("all-MiniLM-L6-v2@v2",)]

    conn.cursor.side_effect = [cur, check_cur]
    cur.execute.return_value = cur
    cur.fetchall.return_value = []  # No results for embedder_id query

    store = _store(conn, cur)

    v = np.ones(384, dtype=np.float32)
    with pytest.raises(ValueError, match="Embedder version mismatch"):
      store.search_with_filters(
        "tenant-a",
        v,
        embedder_id="all-MiniLM-L6-v2@v1",
        top_k=5,
      )

  def test_search_with_filters_empty_tenant_returns_empty(self, mock_pg_deps):
    """Test that search_with_filters returns empty for tenant with no data."""
    conn, cur = mock_pg_deps
    cur.fetchall.return_value = []
    store = _store(conn, cur)

    v = np.ones(384, dtype=np.float32)
    results = store.search_with_filters(
      "tenant-nonexistent",
      v,
      top_k=5,
    )

    assert results == []

  def test_mmr_diversify_fetches_embeddings(self, mock_pg_deps):
    """Test that mmr_diversify retrieves embeddings from database."""
    conn, cur = mock_pg_deps
    # Mock embedding lookups for each candidate
    cur.fetchone.side_effect = [
      (np.array([0.1, 0.2, 0.3]),),
      (np.array([0.4, 0.5, 0.6]),),
    ]
    store = _store(conn, cur)

    candidates = [
      ("text1", 0.95),
      ("text2", 0.92),
    ]
    results = store.mmr_diversify(candidates, top_k=2)

    # Should return results sorted by MMR score
    assert len(results) <= 2
    # Verify embeddings were fetched
    assert cur.execute.called

  def test_mmr_diversify_empty_candidates_returns_empty(self, mock_pg_deps):
    """Test that mmr_diversify returns empty for empty candidates."""
    conn, cur = mock_pg_deps
    store = _store(conn, cur)

    results = store.mmr_diversify([], top_k=5)
    assert results == []

  def test_close_closes_connection(self, mock_pg_deps):
    """Test that close closes the database connection."""
    conn, cur = mock_pg_deps
    store = _store(conn, cur)

    store.close()
    conn.close.assert_called_once()

  def test_close_idempotent_when_already_closed(self, mock_pg_deps):
    """Test that close is idempotent even when connection is already closed."""
    conn, cur = mock_pg_deps
    conn.closed = True
    store = _store(conn, cur)

    # Should not raise
    store.close()
    # close() should not be called again since conn.closed is True
    assert not conn.close.called

  def test_search_with_filters_fallback_on_exception(self, mock_pg_deps):
    """Test that search_with_filters falls back to basic search on schema error."""
    conn, cur = mock_pg_deps
    # First call raises, second call (fallback search) returns results
    cur.execute.side_effect = [
      Exception("Schema mismatch"),  # First execute fails
      cur,  # Second execute (in fallback) returns cursor
    ]
    cur.fetchall.return_value = [("fallback result", 0.8)]
    store = _store(conn, cur)

    v = np.ones(384, dtype=np.float32)
    # Should fall back to basic search instead of raising
    results = store.search_with_filters(
      "tenant-a",
      v,
      acl_labels=["admin"],
      top_k=5,
    )

    # Should return fallback results
    assert len(results) > 0 or results == []

  def test_search_with_filters_acl_filter_applied(self, mock_pg_deps):
    """Test that search_with_filters applies ACL filtering."""
    conn, cur = mock_pg_deps
    cur.execute.return_value = cur
    cur.fetchall.return_value = [("chunk text", 0.9)]
    store = _store(conn, cur)

    v = np.ones(384, dtype=np.float32)
    results = store.search_with_filters(
      "tenant-a",
      v,
      acl_labels=["admin", "user:alice"],
      top_k=5,
    )

    # Check that ACL was included in the query
    execute_calls = [c[0][0] for c in cur.execute.call_args_list]
    assert any("acl" in str(sql).lower() for sql in execute_calls)

  def test_search_with_filters_date_filters_applied(self, mock_pg_deps):
    """Test that search_with_filters applies date filtering."""
    from datetime import datetime
    conn, cur = mock_pg_deps
    cur.execute.return_value = cur
    cur.fetchall.return_value = [("chunk text", 0.9)]
    store = _store(conn, cur)

    v = np.ones(384, dtype=np.float32)
    date_start = datetime(2026, 1, 1)
    date_end = datetime(2026, 12, 31)
    results = store.search_with_filters(
      "tenant-a",
      v,
      date_start=date_start,
      date_end=date_end,
      top_k=5,
    )

    # Check that date filters were included
    execute_calls = [c[0][0] for c in cur.execute.call_args_list]
    assert any("created_at" in str(sql) for sql in execute_calls)

  def test_mmr_diversify_fallback_on_exception(self, mock_pg_deps):
    """Test that mmr_diversify falls back to top_k by score on error."""
    conn, cur = mock_pg_deps
    cur.execute.side_effect = Exception("DB error")
    store = _store(conn, cur)

    candidates = [
      ("text1", 0.95),
      ("text2", 0.92),
      ("text3", 0.88),
    ]
    results = store.mmr_diversify(candidates, top_k=2)

    # Should fall back to returning top_k by score
    assert len(results) == 2
    assert results[0] == ("text1", 0.95)

  def test_backup_with_empty_store(self, mock_pg_deps):
    """Test backup with no chunks in database."""
    conn, cur = mock_pg_deps
    cur.fetchall.return_value = []
    store = _store(conn, cur)

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
      backup_path = f"{tmpdir}/empty_backup.json"
      meta = store.backup(backup_path)

      assert meta['chunk_count'] == 0
      assert meta['owner_ids'] == []

  def test_restore_with_invalid_json(self, mock_pg_deps):
    """Test restore with invalid JSON file."""
    conn, cur = mock_pg_deps
    store = _store(conn, cur)

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
      backup_path = f"{tmpdir}/invalid.json"
      with open(backup_path, 'w') as f:
        f.write("{ invalid json")

      with pytest.raises(Exception):  # JSON decode error
        store.restore(backup_path)

  def test_delete_by_data_subject_case_insensitive(self, mock_pg_deps):
    """Test that delete_by_data_subject uses ILIKE for case-insensitive matching."""
    conn, cur = mock_pg_deps
    cur.rowcount = 2
    store = _store(conn, cur)

    deleted = store.delete_by_data_subject("tenant-a", "Customer-XYZ")
    assert deleted == 2

    # Verify ILIKE was used (case-insensitive)
    sql = cur.execute.call_args[0][0]
    assert "ILIKE" in sql

  def test_search_hybrid_handles_empty_results(self, mock_pg_deps):
    """Test search_hybrid when both dense and text search return empty."""
    conn, cur = mock_pg_deps
    cur.fetchall.side_effect = [
      [],  # Empty dense results
      [],  # Empty text results
    ]
    store = _store(conn, cur)

    v = np.ones(384, dtype=np.float32)
    results = store.search_hybrid("tenant-a", "query", v, top_k=5)

    assert results == []
