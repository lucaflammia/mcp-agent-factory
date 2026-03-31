---
estimated_steps: 15
estimated_files: 3
skills_used: []
---

# T01: Implement IngestionWorker and wire WriterAgent optional bus publish

Create knowledge/ingest.py with IngestionWorker and add optional bus parameter to WriterAgent.

Steps:
1. Create `src/mcp_agent_factory/knowledge/ingest.py`:
   - `IngestionWorker.__init__(self, bus, store, embedder)` — stores refs; subscribes to `agent.output.final` on `bus`; saves the returned queue as `self._queue`.
   - `async start(self)` — loops with `await self._queue.get()`; calls `await self._process(msg)` for each; handles `asyncio.CancelledError` cleanly by breaking.
   - `async _process(self, msg: AgentMessage)` — reads `text = msg.content["text"]` and `owner_id = msg.content["owner_id"]`; splits on `\n\n`; filters empty chunks; calls `store.upsert(owner_id, chunk, embedder.embed(chunk))` for each non-empty chunk.
   - Use tab indentation throughout.
2. Update `__init__.py` at `src/mcp_agent_factory/knowledge/__init__.py` to re-export `IngestionWorker`.
3. Edit `src/mcp_agent_factory/agents/writer.py`:
   - Add `__init__(self, bus=None)` with `self._bus = bus`.
   - Add `owner_id: str = ""` as keyword argument to `run()` after existing positional args.
   - After constructing `report_text` (before the return statement), add: if `self._bus` is not None, publish `AgentMessage(topic="agent.output.final", sender="writer-agent", content={"text": report_text, "owner_id": owner_id, "session_key": analysis.session_key})`.
   - Import `AgentMessage` and `MessageBus` lazily inside the if-block to avoid circular imports: `from mcp_agent_factory.messaging.bus import AgentMessage`.
   - Do NOT change the existing `run()` positional signature — `owner_id` must be keyword-only or default `""`.
   - Tab indentation throughout.

## Inputs

- ``src/mcp_agent_factory/knowledge/vector_store.py``
- ``src/mcp_agent_factory/knowledge/embedder.py``
- ``src/mcp_agent_factory/knowledge/__init__.py``
- ``src/mcp_agent_factory/messaging/bus.py``
- ``src/mcp_agent_factory/agents/writer.py``

## Expected Output

- ``src/mcp_agent_factory/knowledge/ingest.py``
- ``src/mcp_agent_factory/knowledge/__init__.py``
- ``src/mcp_agent_factory/agents/writer.py``

## Verification

PYTHONPATH=src python -c "from mcp_agent_factory.knowledge.ingest import IngestionWorker; from mcp_agent_factory.agents.writer import WriterAgent; print('imports ok')" && PYTHONPATH=src pytest tests/test_pipeline.py -v
