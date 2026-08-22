"""Tests for reranker module."""
from __future__ import annotations

import pytest
from mcp_agent_factory.knowledge.reranker import NoOpReranker


def test_noop_reranker_returns_top_k():
  reranker = NoOpReranker()
  candidates = [("a", 0.9), ("b", 0.8), ("c", 0.7), ("d", 0.6)]
  result = reranker.rerank("query", candidates, top_k=2)
  assert result == [("a", 0.9), ("b", 0.8)]


def test_noop_reranker_empty_candidates():
  reranker = NoOpReranker()
  result = reranker.rerank("query", [], top_k=5)
  assert result == []


def test_noop_reranker_top_k_larger_than_list():
  reranker = NoOpReranker()
  candidates = [("a", 0.9)]
  result = reranker.rerank("query", candidates, top_k=10)
  assert result == [("a", 0.9)]
