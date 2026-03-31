"""
LibrarianAgent — retrieves relevant knowledge base chunks for a query task.
"""
from __future__ import annotations

from mcp_agent_factory.agents.models import AgentTask, MCPContext, RetrievalResult
from mcp_agent_factory.knowledge.embedder import Embedder
from mcp_agent_factory.knowledge.tools import query_knowledge_base
from mcp_agent_factory.knowledge.vector_store import VectorStore


class LibrarianAgent:
	"""Retrieves relevant context chunks from the vector store for a given task."""

	def __init__(self, store: VectorStore, embedder: Embedder, top_k: int = 5) -> None:
		self._store = store
		self._embedder = embedder
		self._top_k = top_k

	async def run(self, task: AgentTask, ctx: MCPContext) -> RetrievalResult:
		ctx.log(f"librarian: querying knowledge base for '{task.name}'")
		chunks = query_knowledge_base(task.name, task.id, self._store, self._embedder, self._top_k)
		ctx.log(f"librarian: retrieved {len(chunks)} chunk(s)")
		return RetrievalResult(
			session_key=task.id,
			chunks=chunks,
			summary=f"Retrieved {len(chunks)} chunk(s) for query: {task.name}",
		)
