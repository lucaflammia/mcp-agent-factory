"""Cross-encoder reranking — configurable and disableable."""
from __future__ import annotations

from typing import Protocol

import numpy as np


class Reranker(Protocol):
  def rerank(self, query: str, candidates: list[tuple[str, float]], top_k: int = 5) -> list[tuple[str, float]]: ...


class NoOpReranker:
  """Pass-through reranker for unit tests and when reranking is disabled."""

  def rerank(self, query: str, candidates: list[tuple[str, float]], top_k: int = 5) -> list[tuple[str, float]]:
    return candidates[:top_k]


class CrossEncoderReranker:
  """Cross-encoder reranker using sentence-transformers.

  Lazy-loads the model on first use. Default model: cross-encoder/ms-marco-MiniLM-L-6-v2.
  Set enabled=False to fall back to score-order truncation (NoOpReranker behaviour).

  Typical usage: rerank top-50 candidates down to top-5. The cross-encoder
  computes query–passage relevance jointly, which consistently beats bi-encoder
  ranking for short retrieval windows.
  """

  def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2", enabled: bool = True) -> None:
    self._model_name = model_name
    self._model = None
    self.enabled = enabled

  def _load(self):
    if self._model is None:
      from sentence_transformers import CrossEncoder
      self._model = CrossEncoder(self._model_name)

  def rerank(self, query: str, candidates: list[tuple[str, float]], top_k: int = 5) -> list[tuple[str, float]]:
    if not self.enabled or not candidates:
      return candidates[:top_k]
    self._load()
    texts = [text for text, _ in candidates]
    pairs = [(query, t) for t in texts]
    scores = self._model.predict(pairs)
    ranked = sorted(zip(texts, scores.tolist()), key=lambda x: x[1], reverse=True)
    return [(text, float(score)) for text, score in ranked[:top_k]]
