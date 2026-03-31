"""Tests for knowledge/ package: StubEmbedder and InMemoryVectorStore."""
import numpy as np
import pytest

from mcp_agent_factory.knowledge import StubEmbedder, InMemoryVectorStore


@pytest.fixture
def embedder():
    return StubEmbedder()


@pytest.fixture
def store():
    return InMemoryVectorStore()


def test_upsert_and_query_returns_result(embedder, store):
    """Upsert one chunk, query with same vector, assert one result returned."""
    v = embedder.embed("hello world")
    store.upsert("alice", "hello world", v)
    results = store.search("alice", v, top_k=1)
    assert len(results) == 1
    assert results[0][0] == "hello world"


def test_cosine_ranking_correct(embedder, store):
    """Identical text ranks higher than unrelated text."""
    query_text = "machine learning"
    unrelated_text = "banana smoothie recipe"
    v_query = embedder.embed(query_text)
    v_identical = embedder.embed(query_text)
    v_unrelated = embedder.embed(unrelated_text)
    store.upsert("alice", query_text, v_identical)
    store.upsert("alice", unrelated_text, v_unrelated)
    results = store.search("alice", v_query, top_k=2)
    assert len(results) == 2
    texts = [r[0] for r in results]
    assert texts[0] == query_text, f"Expected '{query_text}' first, got '{texts[0]}'"


def test_cross_tenant_isolation(embedder, store):
    """Upsert as alice, query as bob — must return empty."""
    v = embedder.embed("secret data")
    store.upsert("alice", "secret data", v)
    results = store.search("bob", v, top_k=5)
    assert results == []


def test_empty_store_returns_empty(embedder, store):
    """Query on a fresh store returns []."""
    v = embedder.embed("anything")
    results = store.search("alice", v, top_k=3)
    assert results == []


def test_top_k_respected(embedder, store):
    """Upsert 5 chunks, query with top_k=2, assert exactly 2 results."""
    for i in range(5):
        v = embedder.embed(f"document {i}")
        store.upsert("alice", f"document {i}", v)
    query_v = embedder.embed("document 0")
    results = store.search("alice", query_v, top_k=2)
    assert len(results) == 2


def test_stub_embedder_determinism(embedder):
    """embed('foo') twice returns identical vectors."""
    v1 = embedder.embed("foo")
    v2 = embedder.embed("foo")
    assert np.array_equal(v1, v2)
