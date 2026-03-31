# S02: Async Ingestion Worker

**Goal:** Implement IngestionWorker that subscribes to agent.output.final on the MessageBus, chunks text, embeds, and upserts into InMemoryVectorStore. Wire WriterAgent to optionally publish to the bus on completion.
**Demo:** After this: pytest tests/test_ingest.py -v passes; pytest tests/test_pipeline.py still passes (no regressions)

## Tasks
- [x] **T01: Created IngestionWorker (subscribe/chunk/embed/upsert) and wired WriterAgent optional bus publish; 30/30 tests pass** — Create knowledge/ingest.py with IngestionWorker and add optional bus parameter to WriterAgent.

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
  - Estimate: 30m
  - Files: src/mcp_agent_factory/knowledge/ingest.py, src/mcp_agent_factory/knowledge/__init__.py, src/mcp_agent_factory/agents/writer.py
  - Verify: PYTHONPATH=src python -c "from mcp_agent_factory.knowledge.ingest import IngestionWorker; from mcp_agent_factory.agents.writer import WriterAgent; print('imports ok')" && PYTHONPATH=src pytest tests/test_pipeline.py -v
- [x] **T02: Verified tests/test_ingest.py and full suite green — 199/199 tests pass** — Write 6 pytest cases in tests/test_ingest.py covering the IngestionWorker and WriterAgent bus integration.

Test cases (all use pytest-asyncio @pytest.mark.asyncio where needed):
1. `test_worker_ingests_message` — create MessageBus, StubEmbedder, InMemoryVectorStore; construct IngestionWorker; call `await worker._process(msg)` directly with a valid AgentMessage; assert `store.search(owner_id, embedder.embed("some text"), top_k=1)` returns non-empty.
2. `test_worker_chunks_text` — report with 3 double-newline-separated paragraphs → `_process` → search returns up to 3 results (top_k=3).
3. `test_worker_owner_isolation` — process message for owner_id='alice'; search for owner_id='bob' → empty list.
4. `test_worker_ignores_empty_chunks` — report text is `"para1\n\n\n\npara2"` (extra blank lines) → no crash; only 2 non-empty chunks stored.
5. `test_writer_publishes_on_bus_when_set` — construct MessageBus; subscribe to `agent.output.final`; `WriterAgent(bus=bus)`; `await agent.run(analysis, ctx, owner_id='u1')`; assert `queue.get_nowait()` returns AgentMessage with `content["owner_id"] == 'u1'`.
6. `test_writer_no_publish_when_bus_none` — `WriterAgent()` (no bus); run succeeds; no exception raised.

Use the AnalysisResult and MCPContext fixtures from test_pipeline.py as a pattern for constructing test inputs. Tab indentation throughout.
  - Estimate: 30m
  - Files: tests/test_ingest.py
  - Verify: PYTHONPATH=src pytest tests/test_ingest.py -v && PYTHONPATH=src pytest tests/test_pipeline.py -v && PYTHONPATH=src pytest tests/ -v
