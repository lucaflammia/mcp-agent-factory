"""Unit tests for PgVectorStore (no live Postgres needed — patches psycopg)."""
from __future__ import annotations

import sys
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
