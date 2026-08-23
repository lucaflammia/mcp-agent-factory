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
	def upsert(self, owner_id: str, text: str, vector: np.ndarray) -> None:
		...

	def search(self, owner_id: str, query_vector: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]:
		...


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


class PgVectorStore:
	"""pgvector-backed vector store (Neon or any Postgres with vector extension).

	Implements the VectorStore protocol. Schema is auto-created on first use.
	Requires psycopg2-binary and pgvector installed, and a valid DATABASE_URL.
	"""

	_DIM = 384

	def __init__(self, dsn: str) -> None:
		import psycopg2
		from pgvector.psycopg2 import register_vector
		self._conn = psycopg2.connect(dsn)
		self._conn.autocommit = True
		register_vector(self._conn)
		with self._conn.cursor() as cur:
			cur.execute(_CREATE_TABLE_SQL)

	def upsert(self, owner_id: str, text: str, vector: np.ndarray) -> None:
		with self._conn.cursor() as cur:
			cur.execute(
				"INSERT INTO knowledge_chunks (owner_id, content, embedding) VALUES (%s, %s, %s)",
				(owner_id, text, vector.astype(np.float32)),
			)

	def search(self, owner_id: str, query_vector: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]:
		tracer = get_tracer("mcp_gateway.vector_store")
		with tracer.start_as_current_span("agent.pg_vector_store.search") as span:
			span.set_attribute("owner_id", owner_id)
			span.set_attribute("top_k", top_k)
			with self._conn.cursor() as cur:
				cur.execute(
					"""
					SELECT content, 1 - (embedding <=> %s::vector) AS score
					FROM knowledge_chunks
					WHERE owner_id = %s
					ORDER BY embedding <=> %s::vector
					LIMIT %s
					""",
					(query_vector.astype(np.float32), owner_id, query_vector.astype(np.float32), top_k),
				)
				rows = cur.fetchall()
			span.set_attribute("result_count", len(rows))
			return [(row[0], float(row[1])) for row in rows]
