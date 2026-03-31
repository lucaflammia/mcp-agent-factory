from __future__ import annotations

from collections import defaultdict
from typing import Protocol

import numpy as np


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
		entries = self._store.get(owner_id, [])
		if not entries:
			return []
		q_norm = query_vector / (np.linalg.norm(query_vector) + 1e-10)
		results: list[tuple[str, float]] = []
		for text, vec in entries:
			v_norm = vec / (np.linalg.norm(vec) + 1e-10)
			score = float(np.dot(q_norm, v_norm))
			results.append((text, score))
		results.sort(key=lambda x: x[1], reverse=True)
		return results[:top_k]
