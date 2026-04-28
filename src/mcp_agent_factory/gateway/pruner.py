from __future__ import annotations

import os
from typing import Sequence

import numpy as np

from mcp_agent_factory.knowledge.embedder import Embedder

_DEFAULT_THRESHOLD = float(os.environ.get("CONTEXT_PRUNE_THRESHOLD", "0.3"))


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
	norm_a = np.linalg.norm(a)
	norm_b = np.linalg.norm(b)
	if norm_a == 0.0 or norm_b == 0.0:
		return 0.0
	return float(np.dot(a, b) / (norm_a * norm_b))


class ContextPruner:
	"""Drop chunks whose cosine similarity to the query is below threshold."""

	def __init__(self, threshold: float = _DEFAULT_THRESHOLD) -> None:
		self.threshold = threshold

	def prune(
		self,
		query: str,
		chunks: Sequence[str],
		embedder: Embedder,
		threshold: float | None = None,
	) -> list[str]:
		"""Return chunks with cosine similarity >= threshold.

		Falls through cleanly (returns []) when chunks is empty.
		"""
		if not chunks:
			return []
		cutoff = threshold if threshold is not None else self.threshold
		query_vec = embedder.embed(query)
		return [
			chunk
			for chunk in chunks
			if _cosine(query_vec, embedder.embed(chunk)) >= cutoff
		]
