"""Ranking metrics for retrieval quality in RAG evaluation.

These metrics measure the *retriever* independently of the *generator*.
Never average them with generation metrics into a single RAG score.

Metrics:
  recall@k          — fraction of relevant chunks found in top-k results
  MRR               — mean reciprocal rank (position of first relevant chunk)
  nDCG@10           — normalised discounted cumulative gain at k=10
  context_precision — fraction of retrieved chunks that are relevant (precision@k)
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalResult:
  """Per-query retrieval evaluation result."""
  query_id: str
  relevant: frozenset[str]
  retrieved: tuple[str, ...]
  recall_at_1: float
  recall_at_3: float
  recall_at_5: float
  recall_at_10: float
  mrr: float
  ndcg_at_10: float
  context_precision: float

  def to_dict(self) -> dict:
    return {
      "query_id": self.query_id,
      "recall@1": round(self.recall_at_1, 4),
      "recall@3": round(self.recall_at_3, 4),
      "recall@5": round(self.recall_at_5, 4),
      "recall@10": round(self.recall_at_10, 4),
      "mrr": round(self.mrr, 4),
      "ndcg@10": round(self.ndcg_at_10, 4),
      "context_precision": round(self.context_precision, 4),
      "n_relevant": len(self.relevant),
      "n_retrieved": len(self.retrieved),
    }


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
  """Fraction of relevant chunks found in the top-k retrieved results."""
  if not relevant:
    return 1.0
  top_k = retrieved[:k]
  found = sum(1 for c in top_k if c in relevant)
  return found / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
  """Reciprocal rank of the first relevant chunk in the ranked list."""
  for i, chunk_id in enumerate(retrieved, start=1):
    if chunk_id in relevant:
      return 1.0 / i
  return 0.0


def _dcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
  dcg = 0.0
  for i, chunk_id in enumerate(retrieved[:k], start=1):
    if chunk_id in relevant:
      dcg += 1.0 / math.log2(i + 1)
  return dcg


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
  """Normalised discounted cumulative gain at k."""
  actual = _dcg_at_k(retrieved, relevant, k)
  n_ideal = min(len(relevant), k)
  ideal = sum(1.0 / math.log2(i + 1) for i in range(1, n_ideal + 1))
  if ideal == 0:
    return 1.0 if actual == 0 else 0.0
  return min(actual / ideal, 1.0)


def context_precision(retrieved: list[str], relevant: set[str]) -> float:
  """Fraction of retrieved chunks that are actually relevant (precision)."""
  if not retrieved:
    return 0.0
  n_relevant = sum(1 for c in retrieved if c in relevant)
  return n_relevant / len(retrieved)


def evaluate_retrieval(
  query_id: str,
  retrieved: list[str],
  relevant: list[str],
) -> RetrievalResult:
  """Compute all ranking metrics for a single query."""
  rel_set = set(relevant)
  return RetrievalResult(
    query_id=query_id,
    relevant=frozenset(relevant),
    retrieved=tuple(retrieved),
    recall_at_1=recall_at_k(retrieved, rel_set, 1),
    recall_at_3=recall_at_k(retrieved, rel_set, 3),
    recall_at_5=recall_at_k(retrieved, rel_set, 5),
    recall_at_10=recall_at_k(retrieved, rel_set, 10),
    mrr=reciprocal_rank(retrieved, rel_set),
    ndcg_at_10=ndcg_at_k(retrieved, rel_set, 10),
    context_precision=context_precision(retrieved, rel_set),
  )


def aggregate_retrieval_metrics(results: list[RetrievalResult]) -> dict:
  """Average per-query metrics across a set of queries."""
  if not results:
    return {}
  n = len(results)
  return {
    "n": n,
    "recall@1": round(sum(r.recall_at_1 for r in results) / n, 4),
    "recall@3": round(sum(r.recall_at_3 for r in results) / n, 4),
    "recall@5": round(sum(r.recall_at_5 for r in results) / n, 4),
    "recall@10": round(sum(r.recall_at_10 for r in results) / n, 4),
    "mrr": round(sum(r.mrr for r in results) / n, 4),
    "ndcg@10": round(sum(r.ndcg_at_10 for r in results) / n, 4),
    "context_precision": round(sum(r.context_precision for r in results) / n, 4),
  }
