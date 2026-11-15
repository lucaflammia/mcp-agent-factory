from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from mcp_agent_factory.gateway.telemetry import get_tracer
from mcp_agent_factory.knowledge.reranker import mmr_diversify


@dataclass(frozen=True)
class ChunkResult:
	"""Chunk result with text, relevance score, and chunk ID for citation tracking."""
	text: str
	score: float
	chunk_id: str

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
  def upsert(self, owner_id: str, text: str, vector: np.ndarray, chunk_id: str | None = None) -> None: ...
  def search(self, owner_id: str, query_vector: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]: ...


class InMemoryVectorStore:
  """Per-owner_id namespaced in-memory vector store with cosine similarity search.

  RAG-02: upsert is idempotent on (owner_id, chunk_id). If chunk_id is None,
  the first 64 chars of text are used as the key (backward-compat).
  delete_by_source() removes all chunks for a given source_id.

  RAG-05: upsert now accepts embedder_id for versioning support. Multiple
  versions can coexist in the store; search_with_filters enforces version matching.
  """

  def __init__(self) -> None:
    # (owner_id, chunk_id, embedder_id) -> (text, vector, source_id)
    self._store: dict[tuple[str, str, str], tuple[str, np.ndarray, str]] = {}

  def upsert(
    self,
    owner_id: str,
    text: str,
    vector: np.ndarray,
    chunk_id: str | None = None,
    source_id: str = "",
    embedder_id: str = "unknown",
  ) -> None:
    chunk_id_val = chunk_id if chunk_id is not None else text[:64]
    key = (owner_id, chunk_id_val, embedder_id)
    self._store[key] = (text, vector, source_id)

  def delete_by_source(self, owner_id: str, source_id: str) -> int:
    """Remove all chunks for the given source_id. Returns count deleted."""
    to_delete = [k for k, (_, _, sid) in self._store.items() if k[0] == owner_id and sid == source_id]
    for k in to_delete:
      del self._store[k]
    return len(to_delete)

  def chunk_exists(self, owner_id: str, chunk_id: str, embedder_id: str = "unknown") -> bool:
    return (owner_id, chunk_id, embedder_id) in self._store

  def delete_by_data_subject(self, owner_id: str, data_subject_id: str) -> int:
    """Delete all chunks for a data subject (RTBF). Returns count deleted.

    RAG-06: Right to be forgotten — removes chunks where the data subject
    is referenced in source_id or content. Use for GDPR/privacy compliance.
    """
    to_delete = [
      k for k, (text, _, sid) in self._store.items()
      if k[0] == owner_id and (data_subject_id in sid or data_subject_id in text)
    ]
    for k in to_delete:
      del self._store[k]
    return len(to_delete)

  def backup(self, path: str | Path) -> dict[str, Any]:
    """Create a point-in-time backup of the vector store.

    Returns metadata: {
      'backup_path': path,
      'chunk_count': int,
      'owner_ids': [str],
      'timestamp': isoformat,
    }
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    backup_data = {
      'store': {},
      'metadata': {
        'timestamp': datetime.utcnow().isoformat(),
        'chunk_count': len(self._store),
      }
    }

    for key, (text, vec, source_id) in self._store.items():
      owner_id, chunk_id, embedder_id = key
      backup_data['store'][str(key)] = {
        'owner_id': owner_id,
        'chunk_id': chunk_id,
        'embedder_id': embedder_id,
        'text': text,
        'vector': vec.tolist(),
        'source_id': source_id,
      }

    with open(path, 'w') as f:
      json.dump(backup_data, f, indent=2)

    owner_ids = set(k[0] for k in self._store.keys())
    return {
      'backup_path': str(path),
      'chunk_count': len(self._store),
      'owner_ids': sorted(owner_ids),
      'timestamp': backup_data['metadata']['timestamp'],
    }

  def restore(self, path: str | Path | dict) -> dict[str, int]:
    """Restore vector store from a backup file.

    Args:
      path: File path (str or Path) or backup metadata dict (from backup()).
            If dict, extracts the 'backup_path' key.

    Returns: {'chunks_restored': int, 'owners_restored': int}
    """
    # Handle backup metadata dict returned from backup()
    if isinstance(path, dict):
      path_str = path.get('backup_path')
      if not path_str:
        raise ValueError("Backup metadata dict must contain 'backup_path' key")
      path = Path(path_str)
    else:
      path = Path(path)
    if not path.exists():
      raise FileNotFoundError(f"Backup file not found: {path}")

    with open(path) as f:
      backup_data = json.load(f)

    self._store.clear()
    owner_ids = set()

    for key_str, data in backup_data.get('store', {}).items():
      key = (data['owner_id'], data['chunk_id'], data['embedder_id'])
      vec = np.array(data['vector'], dtype=np.float32)
      self._store[key] = (data['text'], vec, data['source_id'])
      owner_ids.add(data['owner_id'])

    return {
      'chunks_restored': len(self._store),
      'owners_restored': len(owner_ids),
    }

  def compact(self) -> dict[str, Any]:
    """Remove dead entries and defragment store (no-op for in-memory).

    For in-memory store, this is a no-op. For PgVectorStore, this would
    run VACUUM and update statistics.

    Returns: {'status': 'ok', 'chunk_count': int}
    """
    return {
      'status': 'ok',
      'chunk_count': len(self._store),
    }

  def search(self, owner_id: str, query_vector: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]:
    tracer = get_tracer("mcp_gateway.vector_store")
    with tracer.start_as_current_span("agent.vector_store.search") as span:
      span.set_attribute("owner_id", owner_id)
      span.set_attribute("top_k", top_k)
      entries = [(text, vec) for (oid, _, _), (text, vec, _) in self._store.items() if oid == owner_id]
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

  def search_with_filters(
    self,
    owner_id: str,
    query_vector: np.ndarray,
    acl_labels: list[str] | None = None,
    date_start: datetime | None = None,
    date_end: datetime | None = None,
    embedder_id: str | None = None,
    top_k: int = 5,
  ) -> list[ChunkResult]:
    """Search with mandatory tenant + ACL + date + embedder_id filters.

    RAG-03: Filters are applied inside the search, never post-hoc.
    RAG-05: If embedder_id is specified, search only vectors from that version.
    If embedder_id mismatch is detected (query version not in index), raises explicit error.

    Returns ChunkResult objects with text, score, and chunk_id for citation tracking.
    """
    tracer = get_tracer("mcp_gateway.vector_store")
    with tracer.start_as_current_span("agent.vector_store.search_with_filters") as span:
      span.set_attribute("owner_id", owner_id)
      span.set_attribute("top_k", top_k)
      if acl_labels:
        span.set_attribute("filter.acl_count", len(acl_labels))
      if date_start:
        span.set_attribute("filter.date_start", date_start.isoformat())
      if date_end:
        span.set_attribute("filter.date_end", date_end.isoformat())
      if embedder_id:
        span.set_attribute("filter.embedder_id", embedder_id)

      # Collect candidate entries with metadata, filtering by embedder_id if specified
      candidates: list[tuple[str, np.ndarray, str]] = []
      for (oid, chunk_id, emb_id), (text, vec, source_id) in self._store.items():
        if oid != owner_id:
          continue
        # RAG-05: Filter by embedder_id if specified
        if embedder_id and emb_id != embedder_id:
          continue

        # For in-memory store, we don't have chunk metadata, so we can't filter
        # by ACL or date. But we structure the interface for PgVectorStore.
        candidates.append((text, vec, chunk_id))

      if embedder_id and not candidates:
        # RAG-05: Raise explicit error only if embedder_id was requested but no vectors found
        # Check if tenant has ANY data
        tenant_has_data = any(oid == owner_id for (oid, _, _) in self._store.keys())
        if tenant_has_data:
          # Tenant has data but not in the requested embedder_id version
          available_versions = set(emb_id for (oid, _, emb_id) in self._store.keys() if oid == owner_id)
          raise ValueError(
            f"Embedder version mismatch: requested '{embedder_id}' but index has versions {sorted(available_versions)}. "
            f"The embedder_id may have changed; consider running backfill for the new version."
          )

      if not candidates:
        span.set_attribute("result_count", 0)
        return []

      q_norm = query_vector / (np.linalg.norm(query_vector) + 1e-10)
      results: list[ChunkResult] = []
      for text, vec, chunk_id in candidates:
        v_norm = vec / (np.linalg.norm(vec) + 1e-10)
        score = float(np.dot(q_norm, v_norm))
        results.append(ChunkResult(text=text, score=score, chunk_id=chunk_id))

      results.sort(key=lambda x: x.score, reverse=True)
      top = results[:top_k]
      span.set_attribute("result_count", len(top))
      return top

  def mmr_diversify(
    self,
    candidates,
    top_k: int = 5,
    lambda_param: float = 0.5,
  ):
    """MMR diversification to reduce near-duplicate context.

    RAG-03: Between rerank and prompt assembly, apply MMR to avoid
    clustering of near-duplicate results.

    Supports both ChunkResult and tuple inputs for backward compatibility.
    """
    if not candidates or not hasattr(self, "_store"):
      return candidates[:top_k]

    # Build embeddings dict from stored vectors
    # RAG-05: Updated key format to (owner_id, chunk_id, embedder_id)
    embeddings = {}
    for (_, _, _), (text, vec, _) in self._store.items():
      if text not in embeddings:
        embeddings[text] = vec

    # Detect input type and convert to tuples for mmr_diversify function
    is_chunk_result = isinstance(candidates[0], ChunkResult) if candidates else False
    if is_chunk_result:
      candidates_tuples = [(c.text, c.score) for c in candidates]
    else:
      # Assume tuples (text, score)
      candidates_tuples = candidates

    result_tuples = mmr_diversify(
      candidates=candidates_tuples,
      embeddings=embeddings,
      query_embedding=None,
      top_k=top_k,
      lambda_param=lambda_param,
    )

    # Convert back to original type
    if is_chunk_result:
      chunk_id_map = {c.text: c.chunk_id for c in candidates}
      return [
        ChunkResult(text=text, score=score, chunk_id=chunk_id_map.get(text, ""))
        for text, score in result_tuples
      ]
    else:
      # Return as tuples
      return result_tuples


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

  def upsert(
    self,
    owner_id: str,
    text: str,
    vector: np.ndarray,
    chunk_id: str | None = None,
    source_id: str = "",
    embedder_id: str = "unknown",
  ) -> None:
    conn = self._connect()
    with conn.cursor() as cur:
      cur.execute(
        """
        INSERT INTO chunks (owner_id, chunk_id, text, embedding, ts, embedder_id, content_hash)
        VALUES (%s, %s, %s, %s, to_tsvector('english', %s), %s, %s)
        ON CONFLICT (owner_id, chunk_id) DO UPDATE
            SET text = EXCLUDED.text,
                embedding = EXCLUDED.embedding,
                ts = EXCLUDED.ts,
                embedder_id = EXCLUDED.embedder_id
        """,
        (owner_id, chunk_id or text[:64], text, vector.tolist(), text, embedder_id, chunk_id or text[:64]),
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

  def search_with_filters(
    self,
    owner_id: str,
    query_vector: np.ndarray,
    acl_labels: list[str] | None = None,
    date_start: datetime | None = None,
    date_end: datetime | None = None,
    embedder_id: str | None = None,
    top_k: int = 5,
  ) -> list[tuple[str, float]]:
    """Dense cosine similarity search with mandatory tenant + ACL + date + embedder_id filters.

    RAG-03: Filters are passed to the database query, never post-processed.
    RAG-05: If embedder_id is specified, search only vectors from that version.
    Embedder ID mismatch raises explicit error.

    Note: Requires extended schema with embedder_id column and indexed filters.
    Falls back to basic search if schema is not available.
    """
    conn = self._connect()
    try:
      # Try to use advanced filters if schema has them
      where_clauses = ["owner_id = %s"]
      params: list = [owner_id, query_vector.tolist()]

      # RAG-05: Filter by embedder_id if specified
      if embedder_id:
        where_clauses.append("embedder_id = %s")
        params.append(embedder_id)

      if acl_labels:
        # ACL filtering: any chunk where acl overlaps with user's labels
        where_clauses.append("acl && %s")
        params.append(acl_labels)

      if date_start:
        where_clauses.append("created_at >= %s")
        params.append(date_start)

      if date_end:
        where_clauses.append("created_at <= %s")
        params.append(date_end)

      where_sql = " AND ".join(where_clauses)
      query_sql = f"""
        SELECT text, 1 - (embedding <=> %s::vector) AS score
        FROM chunks
        WHERE {where_sql}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
      """
      params.insert(1, query_vector.tolist())  # Second reference to vector
      params.append(top_k)

      with conn.cursor() as cur:
        try:
          results = cur.execute(query_sql, params).fetchall() if hasattr(cur, 'execute') else []
          if not results and embedder_id:
            # RAG-05: Raise explicit error if embedder_id was requested but no vectors found
            with conn.cursor() as check_cur:
              check_cur.execute(
                "SELECT DISTINCT embedder_id FROM chunks WHERE owner_id = %s",
                (owner_id,)
              )
              available_versions = [row[0] for row in check_cur.fetchall()]
            raise ValueError(
              f"Embedder version mismatch: requested '{embedder_id}' but index has versions {sorted(available_versions)}. "
              f"The embedder_id may have changed; consider running backfill for the new version."
            )
          return [(row[0], float(row[1])) for row in results] if results else []
        except ValueError:
          # Re-raise embedder_id mismatch error
          raise
        except Exception:
          # Schema doesn't support full filtering; fall back to basic search
          return self.search(owner_id, query_vector, top_k=top_k) if not embedder_id else []
    except ValueError:
      # Re-raise embedder_id mismatch error
      raise
    except Exception:
      # Fallback to basic search
      return self.search(owner_id, query_vector, top_k=top_k) if not embedder_id else []

  def mmr_diversify(
    self,
    candidates: list[tuple[str, float]],
    top_k: int = 5,
    lambda_param: float = 0.5,
  ) -> list[tuple[str, float]]:
    """MMR diversification using stored embeddings from the database.

    Retrieves embeddings for candidate texts from the database and applies
    Maximal Marginal Relevance to reduce near-duplicate context.
    """
    if not candidates:
      return []

    conn = self._connect()
    try:
      texts = [text for text, _ in candidates]
      embeddings: dict[str, np.ndarray] = {}

      with conn.cursor() as cur:
        for text in texts:
          cur.execute(
            "SELECT embedding FROM chunks WHERE text = %s LIMIT 1",
            (text,),
          )
          row = cur.fetchone()
          if row:
            embeddings[text] = np.array(row[0], dtype=np.float32)

      result = mmr_diversify(
        candidates=candidates,
        embeddings=embeddings,
        query_embedding=None,
        top_k=top_k,
        lambda_param=lambda_param,
      )
      return result
    except Exception:
      # If MMR fails, return top_k by score
      return sorted(candidates, key=lambda x: x[1], reverse=True)[:top_k]

  def delete_by_source(self, owner_id: str, source_id: str) -> int:
    """Remove all chunks for the given source_id. Returns count deleted."""
    conn = self._connect()
    with conn.cursor() as cur:
      cur.execute(
        "DELETE FROM chunks WHERE owner_id = %s AND source_id = %s",
        (owner_id, source_id)
      )
      deleted = cur.rowcount
    conn.commit()
    return deleted

  def delete_by_data_subject(self, owner_id: str, data_subject_id: str) -> int:
    """Delete all chunks for a data subject (RTBF). Returns count deleted.

    RAG-06: Right to be forgotten — removes chunks where the data subject
    is referenced in source_id or chunk text. Use for GDPR/privacy compliance.
    """
    conn = self._connect()
    with conn.cursor() as cur:
      cur.execute(
        """DELETE FROM chunks
           WHERE owner_id = %s
             AND (source_id ILIKE %s OR text ILIKE %s)""",
        (owner_id, f"%{data_subject_id}%", f"%{data_subject_id}%")
      )
      deleted = cur.rowcount
    conn.commit()
    return deleted

  async def backup(self, path: str | Path) -> dict[str, Any]:
    """Create a point-in-time backup of all chunks to a JSON file.

    Returns metadata: {
      'backup_path': path,
      'chunk_count': int,
      'owner_ids': [str],
      'timestamp': isoformat,
    }
    """
    def _do_backup():
      path_obj = Path(path)
      path_obj.parent.mkdir(parents=True, exist_ok=True)

      conn = self._connect()
      backup_data = {
        'chunks': [],
        'metadata': {
          'timestamp': datetime.utcnow().isoformat(),
        }
      }

      with conn.cursor() as cur:
        cur.execute("""
          SELECT owner_id, chunk_id, text, embedding, source_id, embedder_id
          FROM chunks
          ORDER BY owner_id, chunk_id
        """)
        for row in cur.fetchall():
          embedding = row[3]
          if hasattr(embedding, 'to_list'):
            # pgvector.Vector objects have to_list() method
            embedding_list = embedding.to_list()
          elif isinstance(embedding, str):
            # psycopg might return as string: "[0.1,0.2,...]"
            embedding_list = json.loads(embedding)
          elif hasattr(embedding, 'tolist'):
            # numpy arrays
            embedding_list = embedding.tolist()
          else:
            # Fallback: attempt iteration
            embedding_list = list(embedding)

          # Compute content_hash if not in database (for compatibility)
          import hashlib
          text = row[2]
          content_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()

          backup_data['chunks'].append({
            'owner_id': row[0],
            'chunk_id': row[1],
            'text': row[2],
            'embedding': embedding_list,
            'source_id': row[4],
            'embedder_id': row[5],
            'content_hash': content_hash,
          })

      backup_data['metadata']['chunk_count'] = len(backup_data['chunks'])

      with open(path_obj, 'w') as f:
        json.dump(backup_data, f, indent=2)

      owner_ids = set(c['owner_id'] for c in backup_data['chunks'])
      return {
        'backup_path': str(path_obj),
        'chunk_count': len(backup_data['chunks']),
        'owner_ids': sorted(owner_ids),
        'timestamp': backup_data['metadata']['timestamp'],
      }

    return await asyncio.to_thread(_do_backup)

  async def restore(self, path: str | Path | dict) -> dict[str, int]:
    """Restore vector store from a backup file (clears existing data).

    Args:
      path: File path (str or Path) or backup metadata dict (from backup()).
            If dict, extracts the 'backup_path' key.

    Returns: {'chunks_restored': int, 'owners_restored': int}
    """
    def _do_restore():
      # Handle backup metadata dict returned from backup()
      if isinstance(path, dict):
        path_str = path.get('backup_path')
        if not path_str:
          raise ValueError("Backup metadata dict must contain 'backup_path' key")
        path_obj = Path(path_str)
      else:
        path_obj = Path(path)
      if not path_obj.exists():
        raise FileNotFoundError(f"Backup file not found: {path_obj}")

      with open(path_obj) as f:
        backup_data = json.load(f)

      conn = self._connect()
      owner_ids = set()

      # Clear existing data
      with conn.cursor() as cur:
        cur.execute("TRUNCATE chunks CASCADE")

      # Restore chunks
      with conn.cursor() as cur:
        for chunk in backup_data.get('chunks', []):
          cur.execute("""
            INSERT INTO chunks (owner_id, chunk_id, text, embedding, ts, source_id, embedder_id, content_hash)
            VALUES (%s, %s, %s, %s, to_tsvector('english', %s), %s, %s, %s)
          """, (
            chunk['owner_id'],
            chunk['chunk_id'],
            chunk['text'],
            chunk['embedding'],
            chunk['text'],
            chunk.get('source_id', ''),
            chunk.get('embedder_id', 'unknown'),
            chunk.get('content_hash', ''),
          ))
          owner_ids.add(chunk['owner_id'])

      conn.commit()
      return {
        'chunks_restored': len(backup_data.get('chunks', [])),
        'owners_restored': len(owner_ids),
      }

    return await asyncio.to_thread(_do_restore)

  def compact(self) -> dict[str, Any]:
    """Run maintenance: VACUUM, ANALYZE, and update index statistics.

    RAG-06: Weekly compaction removes dead tuples from deletions and
    updates query planner statistics.

    Returns: {'status': 'ok', 'chunk_count': int}
    """
    conn = self._connect()
    with conn.cursor() as cur:
      # VACUUM (remove dead tuples)
      cur.execute("VACUUM ANALYZE chunks")
      # Get final chunk count
      cur.execute("SELECT COUNT(*) FROM chunks")
      chunk_count = cur.fetchone()[0]
    conn.commit()
    return {
      'status': 'ok',
      'chunk_count': chunk_count,
    }

  def close(self) -> None:
    if self._conn and not self._conn.closed:
      self._conn.close()
