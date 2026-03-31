---
estimated_steps: 9
estimated_files: 1
skills_used: []
---

# T02: Write tests/test_ingest.py and verify full suite green

Write 6 pytest cases in tests/test_ingest.py covering the IngestionWorker and WriterAgent bus integration.

Test cases (all use pytest-asyncio @pytest.mark.asyncio where needed):
1. `test_worker_ingests_message` — create MessageBus, StubEmbedder, InMemoryVectorStore; construct IngestionWorker; call `await worker._process(msg)` directly with a valid AgentMessage; assert `store.search(owner_id, embedder.embed("some text"), top_k=1)` returns non-empty.
2. `test_worker_chunks_text` — report with 3 double-newline-separated paragraphs → `_process` → search returns up to 3 results (top_k=3).
3. `test_worker_owner_isolation` — process message for owner_id='alice'; search for owner_id='bob' → empty list.
4. `test_worker_ignores_empty_chunks` — report text is `"para1\n\n\n\npara2"` (extra blank lines) → no crash; only 2 non-empty chunks stored.
5. `test_writer_publishes_on_bus_when_set` — construct MessageBus; subscribe to `agent.output.final`; `WriterAgent(bus=bus)`; `await agent.run(analysis, ctx, owner_id='u1')`; assert `queue.get_nowait()` returns AgentMessage with `content["owner_id"] == 'u1'`.
6. `test_writer_no_publish_when_bus_none` — `WriterAgent()` (no bus); run succeeds; no exception raised.

Use the AnalysisResult and MCPContext fixtures from test_pipeline.py as a pattern for constructing test inputs. Tab indentation throughout.

## Inputs

- ``src/mcp_agent_factory/knowledge/ingest.py``
- ``src/mcp_agent_factory/knowledge/__init__.py``
- ``src/mcp_agent_factory/agents/writer.py``
- ``src/mcp_agent_factory/messaging/bus.py``
- ``tests/test_pipeline.py``

## Expected Output

- ``tests/test_ingest.py``

## Verification

PYTHONPATH=src pytest tests/test_ingest.py -v && PYTHONPATH=src pytest tests/test_pipeline.py -v && PYTHONPATH=src pytest tests/ -v
