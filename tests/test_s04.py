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
from mcp_agent_factory.gateway.app import bus, gateway_app, set_embedder, set_vector_store
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
