"""Cross-encoder reranking — configurable and disableable.

RAG-03: Adds MMR (Maximal Marginal Relevance) diversification to reduce
near-duplicate context in the final result set.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np


def mmr_diversify(
    candidates: list[tuple[str, float]],
    embeddings: dict[str, np.ndarray],
    query_embedding: np.ndarray | None = None,
    top_k: int = 5,
    lambda_param: float = 0.5,
) -> list[tuple[str, float]]:
    """Maximal Marginal Relevance diversification.

    Selects top_k results by balancing relevance (original score) and diversity
    (distance to already-selected items). lambda_param ∈ [0, 1] controls the tradeoff:
    - lambda=1: pure relevance (just sort by score)
    - lambda=0: pure diversity (pick most dissimilar items)
    - lambda=0.5 (default): balanced

    Args:
        candidates: list of (text, relevance_score) tuples
        embeddings: dict mapping text -> embedding vector
        query_embedding: optional query vector for reference diversity
        top_k: how many results to select
        lambda_param: relevance vs diversity tradeoff

    Returns:
        top_k diverse results as list of (text, final_score) tuples
    """
    if not candidates or top_k <= 0:
        return candidates[:top_k] if top_k > 0 else []

    # Normalize relevance scores to [0, 1]
    if candidates:
        min_score = min(s for _, s in candidates)
        max_score = max(s for _, s in candidates)
        score_range = max_score - min_score if max_score > min_score else 1.0
        norm_scores = {text: (score - min_score) / score_range for text, score in candidates}
    else:
        norm_scores = {}

    selected = []
    remaining = set(c[0] for c in candidates)

    for _ in range(min(top_k, len(candidates))):
        best_text = None
        best_score = -float("inf")

        for text in remaining:
            rel_score = norm_scores.get(text, 0.0)

            # Compute diversity: average distance to already-selected items
            diversity_score = 0.0
            if selected:
                distances = []
                if text in embeddings:
                    for sel_text, _ in selected:
                        if sel_text in embeddings:
                            emb1 = embeddings[text]
                            emb2 = embeddings[sel_text]
                            e1_norm = emb1 / (np.linalg.norm(emb1) + 1e-10)
                            e2_norm = emb2 / (np.linalg.norm(emb2) + 1e-10)
                            cosine_sim = float(np.dot(e1_norm, e2_norm))
                            distances.append(1.0 - cosine_sim)
                    if distances:
                        diversity_score = np.mean(distances)
            else:
                # For the first item, max out diversity
                diversity_score = 1.0

            # Combine: λ * relevance + (1 - λ) * diversity
            combined_score = lambda_param * rel_score + (1.0 - lambda_param) * diversity_score

            if combined_score > best_score:
                best_score = combined_score
                best_text = text

        if best_text is not None:
            orig_score = next((s for t, s in candidates if t == best_text), 0.0)
            selected.append((best_text, orig_score))
            remaining.discard(best_text)

    return selected


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
