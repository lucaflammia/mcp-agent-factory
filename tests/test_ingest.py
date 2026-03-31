"""
Tests for IngestionWorker.

Covers:
- Subscribes to agent.output.final on the bus
- Processes messages: splits text on double-newline, embeds, upserts
- Filters empty chunks
- Handles CancelledError cleanly in start()
- WriterAgent publishes to bus when bus is provided
- WriterAgent does not publish when no bus (backward compatibility)
"""
from __future__ import annotations

import asyncio

import pytest

from mcp_agent_factory.agents.models import AnalysisResult, MCPContext
from mcp_agent_factory.agents.writer import WriterAgent
from mcp_agent_factory.knowledge.embedder import StubEmbedder
from mcp_agent_factory.knowledge.ingest import IngestionWorker
from mcp_agent_factory.knowledge.vector_store import InMemoryVectorStore
from mcp_agent_factory.messaging.bus import AgentMessage, MessageBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(text: str, owner_id: str = "u1") -> AgentMessage:
	return AgentMessage(
		topic="agent.output.final",
		sender="writer-agent",
		content={"text": text, "owner_id": owner_id, "session_key": "s1"},
	)


# ---------------------------------------------------------------------------
# IngestionWorker unit tests
# ---------------------------------------------------------------------------

class TestIngestionWorker:
	def test_subscribes_to_topic_on_init(self):
		bus = MessageBus()
		store = InMemoryVectorStore()
		embedder = StubEmbedder()
		assert bus.subscriber_count("agent.output.final") == 0
		IngestionWorker(bus, store, embedder)
		assert bus.subscriber_count("agent.output.final") == 1

	@pytest.mark.asyncio
	async def test_process_chunks_and_upserts(self):
		bus = MessageBus()
		store = InMemoryVectorStore()
		embedder = StubEmbedder()
		worker = IngestionWorker(bus, store, embedder)

		msg = _make_message("Hello world\n\nSecond chunk\n\nThird chunk", owner_id="alice")
		await worker._process(msg)

		results = store.search("alice", embedder.embed("Hello world"), top_k=10)
		texts = [r[0] for r in results]
		assert "Hello world" in texts
		assert "Second chunk" in texts
		assert "Third chunk" in texts

	@pytest.mark.asyncio
	async def test_process_filters_empty_chunks(self):
		bus = MessageBus()
		store = InMemoryVectorStore()
		embedder = StubEmbedder()
		worker = IngestionWorker(bus, store, embedder)

		# Multiple consecutive newlines produce empty strings after split
		msg = _make_message("Only chunk\n\n\n\n", owner_id="bob")
		await worker._process(msg)

		results = store.search("bob", embedder.embed("Only chunk"), top_k=10)
		assert len(results) == 1
		assert results[0][0] == "Only chunk"

	@pytest.mark.asyncio
	async def test_start_processes_published_message(self):
		bus = MessageBus()
		store = InMemoryVectorStore()
		embedder = StubEmbedder()
		worker = IngestionWorker(bus, store, embedder)

		task = asyncio.create_task(worker.start())
		bus.publish("agent.output.final", _make_message("Pub chunk", owner_id="carol"))
		# Give the event loop a moment to process
		await asyncio.sleep(0)
		await asyncio.sleep(0)
		task.cancel()
		try:
			await task
		except asyncio.CancelledError:
			pass

		results = store.search("carol", embedder.embed("Pub chunk"), top_k=5)
		assert len(results) >= 1
		assert results[0][0] == "Pub chunk"

	@pytest.mark.asyncio
	async def test_start_handles_cancelled_error_cleanly(self):
		bus = MessageBus()
		store = InMemoryVectorStore()
		embedder = StubEmbedder()
		worker = IngestionWorker(bus, store, embedder)

		task = asyncio.create_task(worker.start())
		await asyncio.sleep(0)
		task.cancel()
		# Should not raise
		try:
			await task
		except asyncio.CancelledError:
			pass  # acceptable — task may re-raise after cancel depending on timing

	@pytest.mark.asyncio
	async def test_multiple_owners_isolated(self):
		bus = MessageBus()
		store = InMemoryVectorStore()
		embedder = StubEmbedder()
		worker = IngestionWorker(bus, store, embedder)

		await worker._process(_make_message("Doc A", owner_id="owner1"))
		await worker._process(_make_message("Doc B", owner_id="owner2"))

		r1 = store.search("owner1", embedder.embed("Doc A"), top_k=5)
		r2 = store.search("owner2", embedder.embed("Doc B"), top_k=5)
		texts1 = [r[0] for r in r1]
		texts2 = [r[0] for r in r2]
		assert "Doc A" in texts1
		assert "Doc B" not in texts1
		assert "Doc B" in texts2
		assert "Doc A" not in texts2


# ---------------------------------------------------------------------------
# WriterAgent bus integration tests
# ---------------------------------------------------------------------------

class TestWriterAgentBusIntegration:
	def _make_analysis(self) -> AnalysisResult:
		return AnalysisResult(
			session_key="sess-1",
			summary="Test summary",
			metrics={"x": 1.0},
			trends=["trend1"],
		)

	def _make_ctx(self) -> MCPContext:
		return MCPContext(tool_name="writer")

	@pytest.mark.asyncio
	async def test_writer_publishes_to_bus_when_bus_provided(self):
		bus = MessageBus()
		queue = bus.subscribe("agent.output.final")
		agent = WriterAgent(bus=bus)

		await agent.run(self._make_analysis(), self._make_ctx(), owner_id="u1")

		assert not queue.empty()
		msg = queue.get_nowait()
		assert msg.topic == "agent.output.final"
		assert msg.sender == "writer-agent"
		assert msg.content["owner_id"] == "u1"
		assert msg.content["session_key"] == "sess-1"
		assert "# Analysis Report" in msg.content["text"]

	@pytest.mark.asyncio
	async def test_writer_no_publish_without_bus(self):
		bus = MessageBus()
		queue = bus.subscribe("agent.output.final")
		agent = WriterAgent()  # no bus

		await agent.run(self._make_analysis(), self._make_ctx(), owner_id="u1")

		assert queue.empty()

	@pytest.mark.asyncio
	async def test_writer_backward_compat_no_owner_id(self):
		"""owner_id defaults to '' — no error when not passed."""
		agent = WriterAgent()
		result = await agent.run(self._make_analysis(), self._make_ctx())
		assert result.report_text is not None

	@pytest.mark.asyncio
	async def test_ingestion_worker_receives_writer_output(self):
		"""Full integration: WriterAgent → bus → IngestionWorker → store."""
		bus = MessageBus()
		store = InMemoryVectorStore()
		embedder = StubEmbedder()
		worker = IngestionWorker(bus, store, embedder)

		task = asyncio.create_task(worker.start())

		agent = WriterAgent(bus=bus)
		await agent.run(self._make_analysis(), self._make_ctx(), owner_id="integration-user")

		await asyncio.sleep(0)
		await asyncio.sleep(0)
		task.cancel()
		try:
			await task
		except asyncio.CancelledError:
			pass

		results = store.search("integration-user", embedder.embed("# Analysis Report"), top_k=10)
		assert len(results) >= 1
