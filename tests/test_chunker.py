"""Tests for structure-aware chunker."""
from __future__ import annotations

import pytest
from mcp_agent_factory.knowledge.chunker import chunk_text


def test_short_text_returns_single_chunk():
  chunks = chunk_text("Hello world.", source="doc.txt", chunk_size=512, overlap=64)
  assert len(chunks) == 1
  assert chunks[0].text == "Hello world."
  assert chunks[0].metadata["source"] == "doc.txt"


def test_paragraph_split():
  text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
  chunks = chunk_text(text, chunk_size=512, overlap=64)
  assert len(chunks) >= 1
  combined = " ".join(c.text for c in chunks)
  assert "First paragraph" in combined
  assert "Second paragraph" in combined


def test_large_text_splits_into_multiple_chunks():
  text = "\n\n".join(f"Paragraph number {i} with some content here." for i in range(20))
  chunks = chunk_text(text, chunk_size=200, overlap=20)
  assert len(chunks) > 1


def test_overlap_carries_content():
  """Last chunk should share some content with the previous chunk."""
  text = "\n\n".join(f"Sentence {i}." for i in range(30))
  chunks = chunk_text(text, chunk_size=100, overlap=30)
  if len(chunks) >= 2:
    texts = [c.text for c in chunks]
    found_overlap = any(
      any(word in texts[i + 1] for word in texts[i].split())
      for i in range(len(texts) - 1)
    )
    assert found_overlap


def test_metadata_records_hyperparams():
  chunks = chunk_text("Some text here.", chunk_size=256, overlap=32)
  assert chunks[0].metadata["chunk_size"] == 256
  assert chunks[0].metadata["overlap"] == 32


def test_empty_text_returns_chunk():
  chunks = chunk_text("", source="x")
  assert len(chunks) == 1


def test_rrf_fusion():
  from mcp_agent_factory.knowledge.vector_store import _rrf_fusion
  dense = [("A", 0.9), ("B", 0.8), ("C", 0.7)]
  text = [("B", 0.6), ("D", 0.5), ("A", 0.4)]
  result = _rrf_fusion(dense, text, top_k=3)
  texts = [r[0] for r in result]
  assert texts[0] in ("A", "B")
  assert texts[1] in ("A", "B")
  assert "D" in texts or "C" in texts
