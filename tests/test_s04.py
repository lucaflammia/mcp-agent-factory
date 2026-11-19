"""
S04 tests: query_knowledge_base tool, LibrarianAgent, gateway wiring, and SSE event.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

import mcp_agent_factory.gateway.app as gateway_module
from mcp_agent_factory.agents.librarian import LibrarianAgent
from mcp_agent_factory.agents.models import AgentTask, MCPContext, RetrievalResult
from mcp_agent_factory.gateway.app import (
	bus,
	gateway_app,
	set_embedder,
	set_pruner,
	set_vector_store,
)
from mcp_agent_factory.gateway.pruner import ContextPruner
from mcp_agent_factory.knowledge import (
	InMemoryVectorStore,
	StubEmbedder,
	query_knowledge_base,
)
from mcp_agent_factory.server_http import TOOLS

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _populated_store():
	embedder = StubEmbedder()
	store = InMemoryVectorStore()
	# Upsert directly — IngestionWorker requires a bus arg, so bypass it here
	store.upsert("alice", "prior analysis about climate", embedder.embed("prior analysis about climate"))
	return store, embedder


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_query_knowledge_base_returns_chunks():
	store, embedder = _populated_store()
	result = query_knowledge_base("climate", "alice", store, embedder)
	assert len(result) > 0
	assert result[0]["text"] == "prior analysis about climate"
	assert "score" in result[0]


def test_query_knowledge_base_empty_store():
	embedder = StubEmbedder()
	store = InMemoryVectorStore()
	result = query_knowledge_base("climate", "alice", store, embedder)
	assert result == []


def test_librarian_agent_run():
	store, embedder = _populated_store()
	librarian = LibrarianAgent(store, embedder)
	task = AgentTask(id="alice", name="climate", payload={})
	ctx = MCPContext(tool_name="test")
	result = asyncio.run(librarian.run(task, ctx))
	assert isinstance(result, RetrievalResult)
	assert result.session_key == "alice"
	assert len(result.chunks) >= 1
	assert "Retrieved" in result.summary


def test_gateway_tool_registered():
	names = [t["name"] for t in TOOLS]
	assert "query_knowledge_base" in names


def test_gateway_query_knowledge_base_dev_mode(monkeypatch):
	# Populate under 'dev' — dev mode resolves owner_id to 'dev' (no JWT claims)
	embedder = StubEmbedder()
	store = InMemoryVectorStore()
	store.upsert("dev", "prior analysis about climate", embedder.embed("prior analysis about climate"))
	set_vector_store(store)
	set_embedder(embedder)
	# StubEmbedder uses random projections — disable semantic pruning so the test chunk passes through.
	set_pruner(ContextPruner(threshold=-1.0))  # StubEmbedder gives random cosines; -1.0 passes all
	monkeypatch.setattr(gateway_module, "DEV_MODE", True)

	client = TestClient(gateway_app)
	resp = client.post("/mcp", json={
		"jsonrpc": "2.0",
		"id": 1,
		"method": "tools/call",
		"params": {
			"name": "query_knowledge_base",
			"arguments": {"query": "climate", "top_k": 3},
		},
	})
	assert resp.status_code == 200
	text = resp.json()["result"]["content"][0]["text"]
	assert len(text) > 2  # non-empty result (not "[]")


def test_gateway_emits_sse_event(monkeypatch):
	store, embedder = _populated_store()
	set_vector_store(store)
	set_embedder(embedder)
	monkeypatch.setattr(gateway_module, "DEV_MODE", True)

	q = bus.subscribe("knowledge.retrieved")

	client = TestClient(gateway_app)
	client.post("/mcp", json={
		"jsonrpc": "2.0",
		"id": 2,
		"method": "tools/call",
		"params": {
			"name": "query_knowledge_base",
			"arguments": {"query": "climate", "top_k": 3},
		},
	})

	assert not q.empty(), "Expected knowledge.retrieved event on bus"
	msg = q.get_nowait()
	assert msg.topic == "knowledge.retrieved"
	assert msg.content["owner_id"] == "dev"  # no JWT claims → 'dev'


def test_cross_tenant_isolation_via_gateway(monkeypatch):
	"""Chunks stored under 'alice' are not returned when owner_id resolves to 'dev'."""
	store, embedder = _populated_store()
	set_vector_store(store)
	set_embedder(embedder)
	monkeypatch.setattr(gateway_module, "DEV_MODE", True)

	client = TestClient(gateway_app)
	resp = client.post("/mcp", json={
		"jsonrpc": "2.0",
		"id": 3,
		"method": "tools/call",
		"params": {
			"name": "query_knowledge_base",
			"arguments": {"query": "climate", "top_k": 5},
		},
	})
	assert resp.status_code == 200
	text = resp.json()["result"]["content"][0]["text"]
	assert text == "[]"


# ---------------------------------------------------------------------------
# Coverage: hybrid search, exception path, fallback tracer
# ---------------------------------------------------------------------------

def test_query_knowledge_base_hybrid_search():
	"""use_hybrid=True routes through search_hybrid when the store exposes it."""
	store, embedder = _populated_store()

	calls = []

	def _search_hybrid(owner_id, query, vector, top_k):
		calls.append((owner_id, query, top_k))
		return store.search(owner_id, vector, top_k=top_k)

	store.search_hybrid = _search_hybrid
	result = query_knowledge_base("climate", "alice", store, embedder, use_hybrid=True)
	assert len(calls) == 1
	assert calls[0][0] == "alice"
	assert len(result) > 0


def test_query_knowledge_base_hybrid_fallback_when_no_method():
	"""use_hybrid=True but store lacks search_hybrid — falls back to dense search."""
	store, embedder = _populated_store()
	if hasattr(store, "search_hybrid"):
		delattr(store, "search_hybrid")
	result = query_knowledge_base("climate", "alice", store, embedder, use_hybrid=True)
	assert isinstance(result, list)


def test_query_knowledge_base_exception_propagates():
	"""Exceptions from embed() propagate out of query_knowledge_base."""
	embedder = StubEmbedder()
	store = InMemoryVectorStore()

	def _bad_embed(text):
		raise ValueError("embed failed")

	embedder.embed = _bad_embed
	with pytest.raises(ValueError, match="embed failed"):
		query_knowledge_base("anything", "alice", store, embedder)


def test_query_knowledge_base_fallback_tracer(monkeypatch):
	"""When opentelemetry is absent the fallback tracer is used (no crash)."""
	import sys
	import importlib

	otel_modules = {k: v for k, v in sys.modules.items() if k.startswith("opentelemetry")}
	for k in otel_modules:
		sys.modules[k] = None  # type: ignore[assignment]

	try:
		import mcp_agent_factory.knowledge.tools as tools_mod
		importlib.reload(tools_mod)
		store, embedder = _populated_store()
		result = tools_mod.query_knowledge_base("climate", "alice", store, embedder)
		assert isinstance(result, list)
	finally:
		for k in otel_modules:
			sys.modules[k] = otel_modules[k]
		importlib.reload(tools_mod)
