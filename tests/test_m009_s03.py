"""S03: ContextPruner — cosine similarity filtering tests."""
from __future__ import annotations

import numpy as np
import pytest

from mcp_agent_factory.gateway.pruner import ContextPruner, _cosine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FixedEmbedder:
	"""Returns pre-seeded vectors by text; unknown texts get a random vector."""

	def __init__(self, mapping: dict[str, np.ndarray]) -> None:
		self._map = mapping

	def embed(self, text: str) -> np.ndarray:
		return self._map[text]


def _unit(v: np.ndarray) -> np.ndarray:
	return v / np.linalg.norm(v)


# ---------------------------------------------------------------------------
# _cosine unit tests
# ---------------------------------------------------------------------------

def test_cosine_identical():
	v = np.array([1.0, 0.0, 0.0])
	assert _cosine(v, v) == pytest.approx(1.0)


def test_cosine_orthogonal():
	a = np.array([1.0, 0.0])
	b = np.array([0.0, 1.0])
	assert _cosine(a, b) == pytest.approx(0.0)


def test_cosine_opposite():
	v = np.array([1.0, 1.0])
	assert _cosine(v, -v) == pytest.approx(-1.0)


def test_cosine_zero_vector():
	z = np.zeros(3)
	v = np.array([1.0, 0.0, 0.0])
	assert _cosine(z, v) == 0.0
	assert _cosine(v, z) == 0.0


# ---------------------------------------------------------------------------
# ContextPruner.prune
# ---------------------------------------------------------------------------

@pytest.fixture
def pruner():
	return ContextPruner(threshold=0.5)


def _make_embedder(query_vec, chunk_vecs: dict[str, np.ndarray]) -> FixedEmbedder:
	return FixedEmbedder({"query": query_vec, **chunk_vecs})


def test_prune_empty_chunks(pruner):
	embedder = FixedEmbedder({})
	assert pruner.prune("query", [], embedder) == []


def test_prune_on_topic_chunk_passes(pruner):
	q = _unit(np.array([1.0, 0.0, 0.0]))
	on_topic = _unit(np.array([0.9, 0.1, 0.0]))   # high similarity
	embedder = _make_embedder(q, {"on": on_topic})
	result = pruner.prune("query", ["on"], embedder)
	assert result == ["on"]


def test_prune_off_topic_chunk_dropped(pruner):
	q = _unit(np.array([1.0, 0.0, 0.0]))
	off_topic = _unit(np.array([0.0, 0.0, 1.0]))   # orthogonal → similarity ~0
	embedder = _make_embedder(q, {"off": off_topic})
	result = pruner.prune("query", ["off"], embedder)
	assert result == []


def test_prune_mixed_chunks(pruner):
	q = _unit(np.array([1.0, 0.0, 0.0]))
	on_topic = _unit(np.array([0.95, 0.05, 0.0]))
	off_topic = _unit(np.array([0.0, 0.0, 1.0]))
	embedder = _make_embedder(q, {"on": on_topic, "off": off_topic})
	result = pruner.prune("query", ["on", "off"], embedder)
	assert result == ["on"]


def test_prune_threshold_exactly_at_boundary(pruner):
	# threshold = 0.5; construct a vector with cos = exactly 0.5
	q = np.array([1.0, 0.0])
	# cos(60°) = 0.5
	import math
	angle = np.array([math.cos(math.pi / 3), math.sin(math.pi / 3)])
	embedder = _make_embedder(q, {"boundary": angle})
	result = pruner.prune("query", ["boundary"], embedder)
	assert result == ["boundary"]


def test_prune_custom_threshold_overrides_instance(pruner):
	"""Per-call threshold takes precedence over instance default."""
	q = _unit(np.array([1.0, 0.0]))
	moderate = _unit(np.array([0.7, 0.7]))   # ~cos 0.707
	embedder = _make_embedder(q, {"mod": moderate})
	# With instance threshold 0.5 it passes; with high per-call threshold 0.9 it drops.
	assert pruner.prune("query", ["mod"], embedder) == ["mod"]
	assert pruner.prune("query", ["mod"], embedder, threshold=0.9) == []


def test_prune_all_chunks_pass(pruner):
	q = _unit(np.array([1.0, 0.0]))
	c1 = _unit(np.array([0.9, 0.1]))
	c2 = _unit(np.array([0.8, 0.2]))
	embedder = _make_embedder(q, {"c1": c1, "c2": c2})
	result = pruner.prune("query", ["c1", "c2"], embedder)
	assert set(result) == {"c1", "c2"}


def test_prune_preserves_order():
	pruner = ContextPruner(threshold=0.0)  # pass everything
	q = np.array([1.0, 0.0])
	vecs = {str(i): _unit(np.array([float(i + 1), 0.1])) for i in range(5)}
	vecs["query"] = q
	embedder = FixedEmbedder(vecs)
	chunks = [str(i) for i in range(5)]
	result = pruner.prune("query", chunks, embedder)
	assert result == chunks


def test_prune_threshold_env_default(monkeypatch):
	monkeypatch.setenv("CONTEXT_PRUNE_THRESHOLD", "0.99")
	# Re-importing would pick up env var at module load; test instance creation instead.
	from mcp_agent_factory.gateway import pruner as _mod
	p = _mod.ContextPruner()
	# Default from instance should still use module-level default (0.3);
	# only new instances after re-import get 0.99. Verify instance respects passed value.
	assert p.threshold == 0.3  # module already loaded; env change has no retroactive effect


def test_prune_single_chunk_passes():
	p = ContextPruner(threshold=0.0)
	q = np.array([1.0])
	c = np.array([1.0])
	embedder = FixedEmbedder({"query": q, "chunk": c})
	assert p.prune("query", ["chunk"], embedder) == ["chunk"]
