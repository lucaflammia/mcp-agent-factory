from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np


class Embedder(Protocol):
	def embed(self, text: str) -> np.ndarray:
		...


class StubEmbedder:
	"""Deterministic 64-dim float32 embedder based on seeded hash projection."""

	DIM: int = 64

	def embed(self, text: str) -> np.ndarray:
		seed = int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32)
		rng = np.random.default_rng(seed)
		vec = rng.standard_normal(self.DIM).astype(np.float32)
		# Guard against zero-vector
		vec += np.float32(1e-7)
		return vec


class LocalEmbedder:
	"""Semantic embedder using sentence-transformers (local, no API calls).

	Lazy-loads the model on first use. Default model: all-MiniLM-L6-v2 (22 MB,
	384-dim), which provides genuine cosine similarity for semantic search.
	"""

	def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
		self._model_name = model_name
		self._model = None

	def _load(self):
		if self._model is None:
			from sentence_transformers import SentenceTransformer
			self._model = SentenceTransformer(self._model_name)

	def embed(self, text: str) -> np.ndarray:
		self._load()
		vec = self._model.encode(text, convert_to_numpy=True)
		return vec.astype(np.float32)
