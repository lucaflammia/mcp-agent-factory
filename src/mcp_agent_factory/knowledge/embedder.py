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
