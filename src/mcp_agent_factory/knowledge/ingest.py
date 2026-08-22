"""
IngestionWorker — subscribes to agent.output.final on MessageBus,
chunks text (structure-aware with overlap), embeds, and upserts into a VectorStore.
"""
from __future__ import annotations

import asyncio
import logging

from mcp_agent_factory.knowledge.chunker import chunk_text

logger = logging.getLogger(__name__)


class IngestionWorker:
  """Listens for agent output messages and ingests them into a vector store.

  Usage::

      worker = IngestionWorker(bus, store, embedder)
      task = asyncio.create_task(worker.start())
      # ... later
      task.cancel()
  """

  def __init__(self, bus, store, embedder, chunk_size: int = 512, overlap: int = 64) -> None:
    self._bus = bus
    self._store = store
    self._embedder = embedder
    self._chunk_size = chunk_size
    self._overlap = overlap
    self._queue = bus.subscribe("agent.output.final")

  async def start(self) -> None:
    try:
      while True:
        msg = await self._queue.get()
        await self._process(msg)
    except asyncio.CancelledError:
      pass

  async def _process(self, msg) -> None:
    text: str = msg.content["text"]
    owner_id: str = msg.content["owner_id"]
    source: str = msg.content.get("source", "")

    chunks = chunk_text(text, source=source, chunk_size=self._chunk_size, overlap=self._overlap)
    for chunk in chunks:
      self._store.upsert(owner_id, chunk.text, self._embedder.embed(chunk.text))

    logger.debug({
      "event": "ingest_processed",
      "owner_id": owner_id,
      "chunk_count": len(chunks),
      "chunk_size": self._chunk_size,
      "overlap": self._overlap,
    })
