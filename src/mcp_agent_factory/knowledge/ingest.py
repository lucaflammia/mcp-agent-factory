"""
IngestionWorker — subscribes to agent.output.final on MessageBus,
chunks text, embeds, and upserts into a VectorStore.

Observability: logs each processed message at DEBUG with owner_id and chunk count.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class IngestionWorker:
	"""
	Listens for agent output messages and ingests them into a vector store.

	Usage::

		worker = IngestionWorker(bus, store, embedder)
		task = asyncio.create_task(worker.start())
		# ... later
		task.cancel()
	"""

	def __init__(self, bus, store, embedder) -> None:
		from mcp_agent_factory.messaging.bus import AgentMessage  # noqa: F401 (type ref)
		self._bus = bus
		self._store = store
		self._embedder = embedder
		self._queue = bus.subscribe("agent.output.final")

	async def start(self) -> None:
		"""Process messages from the queue until cancelled."""
		try:
			while True:
				msg = await self._queue.get()
				await self._process(msg)
		except asyncio.CancelledError:
			pass

	async def _process(self, msg) -> None:
		"""Chunk, embed, and upsert a single agent output message."""
		text: str = msg.content["text"]
		owner_id: str = msg.content["owner_id"]

		chunks = [c for c in text.split("\n\n") if c.strip()]
		for chunk in chunks:
			self._store.upsert(owner_id, chunk, self._embedder.embed(chunk))

		logger.debug({
			"event": "ingest_processed",
			"owner_id": owner_id,
			"chunk_count": len(chunks),
		})
