---
id: S02
parent: M005
milestone: M005
provides:
  - IngestionWorker class in knowledge/ingest.py
  - WriterAgent optional bus integration with owner_id propagation
  - 10 pytest tests covering ingest worker and bus integration
requires:
  - slice: S01
    provides: InMemoryVectorStore, MessageBus, AgentMessage, StubEmbedder
affects:
  - S04
key_files:
  - src/mcp_agent_factory/knowledge/ingest.py
  - src/mcp_agent_factory/knowledge/__init__.py
  - src/mcp_agent_factory/agents/writer.py
  - tests/test_ingest.py
key_decisions:
  - IngestionWorker subscribes during __init__ so subscriber_count is immediately testable without starting the loop
  - Lazy AgentMessage import inside WriterAgent publish block avoids circular imports
  - owner_id as keyword-only arg preserves WriterAgent.run() backward compatibility
patterns_established:
  - MessageBus subscriber pattern: subscribe in __init__, consume in async start() loop, handle CancelledError by breaking
  - Optional bus injection on agents: pass bus=None by default, publish only if set — zero coupling for callers that don't need ingestion
observability_surfaces:
  - none
drill_down_paths:
  - .gsd/milestones/M005/slices/S02/tasks/T01-SUMMARY.md
  - .gsd/milestones/M005/slices/S02/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-31T07:26:53.374Z
blocker_discovered: false
---

# S02: Async Ingestion Worker

**IngestionWorker auto-ingests WriterAgent output into the vector store via MessageBus subscription; 10 new tests + 199 total pass with no regressions.**

## What Happened

T01 created `knowledge/ingest.py` with `IngestionWorker` that subscribes to `agent.output.final` in `__init__`, runs a `start()` loop consuming messages via `await self._queue.get()`, splits content on `\n\n`, filters empty chunks, and upserts each into `InMemoryVectorStore`. `CancelledError` is caught cleanly to stop the loop. `WriterAgent` was extended with an optional `bus` constructor param and a keyword-only `owner_id` arg on `run()`; after building `report_text` it publishes an `AgentMessage` if bus is set, using a lazy import to avoid circular dependencies. T01 also pre-created `tests/test_ingest.py` with 10 test cases covering all behaviours. T02 was verification-only: confirmed 10/10 ingest tests and 199/199 total tests pass.

## Verification

PYTHONPATH=src pytest tests/test_ingest.py -v → 10/10 pass. PYTHONPATH=src pytest tests/test_pipeline.py -v → 20/20 pass. PYTHONPATH=src pytest tests/ -v → 199/199 pass.

## Requirements Advanced

- R102 — IngestionWorker subscribes to agent.output.final, chunks text, and upserts into vector store; WriterAgent publishes on completion when bus is set
- R101 — owner_id is propagated from WriterAgent through AgentMessage content and used as the namespace key in every upsert call

## Requirements Validated

- R102 — test_ingestion_worker_receives_writer_output confirms end-to-end: WriterAgent publishes → IngestionWorker processes → store.search returns chunk; test_multiple_owners_isolated confirms cross-tenant isolation

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

T01 pre-created all 10 tests so T02 became verification-only. Minor: test helper _make_ctx used wrong MCPContext kwargs; corrected after inspecting actual model signature.

## Known Limitations

IngestionWorker.start() must be driven by an external task (asyncio.create_task); it is not auto-started. No back-pressure — if the bus queue fills faster than processing, messages queue unboundedly.

## Follow-ups

None.

## Files Created/Modified

- `src/mcp_agent_factory/knowledge/ingest.py` — New IngestionWorker: subscribe/start/process loop
- `src/mcp_agent_factory/knowledge/__init__.py` — Re-exports IngestionWorker
- `src/mcp_agent_factory/agents/writer.py` — Optional bus param + owner_id kwarg + publish on completion
- `tests/test_ingest.py` — 10 pytest tests covering worker and WriterAgent bus integration
