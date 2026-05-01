from __future__ import annotations

from collections import defaultdict
from typing import Protocol

import numpy as np

from mcp_agent_factory.gateway.telemetry import get_tracer


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
