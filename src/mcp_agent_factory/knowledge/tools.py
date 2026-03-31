"""
Knowledge base query tool — retrieves top-k relevant chunks for a query.
"""
from __future__ import annotations

from mcp_agent_factory.knowledge.embedder import Embedder
from mcp_agent_factory.knowledge.vector_store import VectorStore


def query_knowledge_base(
	query: str,
	owner_id: str,
	store: VectorStore,
	embedder: Embedder,
	top_k: int = 5,
) -> list[dict]:
	"""Embed *query* and return the top-k matching chunks for *owner_id*.

	Returns a list of dicts with ``text`` and ``score`` keys.
	"""
	query_vector = embedder.embed(query)
	results = store.search(owner_id, query_vector, top_k)
	return [{"text": text, "score": score} for text, score in results]
