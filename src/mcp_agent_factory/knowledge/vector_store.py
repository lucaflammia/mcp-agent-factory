from __future__ import annotations

from collections import defaultdict
from typing import Protocol

import numpy as np

from mcp_agent_factory.gateway.telemetry import get_tracer

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id BIGSERIAL PRIMARY KEY,
    owner_id TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384) NOT NULL
);
CREATE INDEX IF NOT EXISTS knowledge_chunks_owner_idx ON knowledge_chunks (owner_id);
"""


class VectorStore(Protocol):
  def upsert(self, owner_id: str, text: str, vector: np.ndarray) -> None: ...
  def search(self, owner_id: str, query_vector: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]: ...


class InMemoryVectorStore:
  """Per-owner_id namespaced in-memory vector store with cosine similarity search."""

  def __init__(self) -> None:
    self._store: dict[str, list[tuple[str, np.ndarray]]] = defaultdict(list)

  def upsert(self, owner_id: str, text: str, vector: np.ndarray) -> None:
    self._store[owner_id].append((text, vector))

  def search(self, owner_id: str, query_vector: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]:
    tracer = get_tracer("mcp_gateway.vector_store")
    with tracer.start_as_current_span("agent.vector_store.search") as span:
      span.set_attribute("owner_id", owner_id)
      span.set_attribute("top_k", top_k)
      entries = self._store.get(owner_id, [])
      if not entries:
        span.set_attribute("result_count", 0)
        return []
      q_norm = query_vector / (np.linalg.norm(query_vector) + 1e-10)
      results: list[tuple[str, float]] = []
      for text, vec in entries:
        v_norm = vec / (np.linalg.norm(vec) + 1e-10)
        score = float(np.dot(q_norm, v_norm))
        results.append((text, score))
      results.sort(key=lambda x: x[1], reverse=True)
      top = results[:top_k]
      span.set_attribute("result_count", len(top))
      return top


def _rrf_fusion(
  dense_results: list[tuple[str, float]],
  text_results: list[tuple[str, float]],
  top_k: int = 5,
  k: int = 60,
) -> list[tuple[str, float]]:
  """Reciprocal Rank Fusion of two ranked lists.

  RRF(d) = Σ 1 / (k + rank_i(d))
  k=60 is the standard default from the original RRF paper.
  No score normalisation needed — avoids naive hybrid scaling bugs.
  """
  scores: dict[str, float] = defaultdict(float)
  for rank, (text, _) in enumerate(dense_results, start=1):
    scores[text] += 1.0 / (k + rank)
  for rank, (text, _) in enumerate(text_results, start=1):
    scores[text] += 1.0 / (k + rank)
  fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
  return [(text, score) for text, score in fused[:top_k]]


class PgVectorStore:
  """Persistent vector store backed by PostgreSQL + pgvector.

  Schema (created by migrations/001_pgvector_init.sql):
      chunks(id, owner_id, chunk_id, text, embedding vector(N), ts tsvector)

  Tenant isolation is structural: owner_id is an indexed column that is
  always included in WHERE clauses. Application code never filters after
  the fact.

  Hybrid search uses dense cosine similarity + Postgres full-text (tsvector)
  fused with Reciprocal Rank Fusion (RRF, k=60).
  """

  def __init__(self, dsn: str, embedding_dim: int = 384) -> None:
    self._dsn = dsn
    self._dim = embedding_dim
    self._conn = None

  def _connect(self):
    if self._conn is None or self._conn.closed:
      try:
        import psycopg
        from pgvector.psycopg import register_vector
      except ImportError as exc:
        raise RuntimeError(
          "psycopg and pgvector are required: pip install 'psycopg[binary]' pgvector"
        ) from exc
      self._conn = psycopg.connect(self._dsn)
      register_vector(self._conn)
    return self._conn

  def upsert(self, owner_id: str, text: str, vector: np.ndarray, chunk_id: str | None = None) -> None:
    conn = self._connect()
    with conn.cursor() as cur:
      cur.execute(
        """
        INSERT INTO chunks (owner_id, chunk_id, text, embedding, ts)
        VALUES (%s, %s, %s, %s, to_tsvector('english', %s))
        ON CONFLICT (owner_id, chunk_id) DO UPDATE
            SET text = EXCLUDED.text,
                embedding = EXCLUDED.embedding,
                ts = EXCLUDED.ts
        """,
        (owner_id, chunk_id or text[:64], text, vector.tolist(), text),
      )
    conn.commit()

  def search(self, owner_id: str, query_vector: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]:
    """Dense cosine similarity search, filtered by owner_id."""
    conn = self._connect()
    with conn.cursor() as cur:
      cur.execute(
        """
        SELECT text, 1 - (embedding <=> %s::vector) AS score
        FROM chunks
        WHERE owner_id = %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (query_vector.tolist(), owner_id, query_vector.tolist(), top_k),
      )
      return [(row[0], float(row[1])) for row in cur.fetchall()]

  def search_text(self, owner_id: str, query: str, top_k: int = 50) -> list[tuple[str, float]]:
    """Full-text (BM25-like) search using Postgres tsvector, filtered by owner_id."""
    conn = self._connect()
    with conn.cursor() as cur:
      cur.execute(
        """
        SELECT text, ts_rank_cd(ts, plainto_tsquery('english', %s)) AS score
        FROM chunks
        WHERE owner_id = %s
          AND ts @@ plainto_tsquery('english', %s)
        ORDER BY score DESC
        LIMIT %s
        """,
        (query, owner_id, query, top_k),
      )
      return [(row[0], float(row[1])) for row in cur.fetchall()]

  def search_hybrid(
    self,
    owner_id: str,
    query: str,
    query_vector: np.ndarray,
    top_k: int = 5,
    dense_k: int = 50,
    rrf_k: int = 60,
  ) -> list[tuple[str, float]]:
    """Hybrid dense + full-text search with Reciprocal Rank Fusion."""
    dense = self.search(owner_id, query_vector, top_k=dense_k)
    text = self.search_text(owner_id, query, top_k=dense_k)
    return _rrf_fusion(dense, text, top_k=top_k, k=rrf_k)

  def close(self) -> None:
    if self._conn and not self._conn.closed:
      self._conn.close()
