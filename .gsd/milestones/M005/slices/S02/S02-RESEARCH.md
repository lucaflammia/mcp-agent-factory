# S02: Async Ingestion Worker — Research

**Date:** 2026-03-31

## Summary

S02 is well-understood work that wires the existing `MessageBus` and `knowledge/` package (from S01) together via an `IngestionWorker`. The pattern is a straight application of code already in the codebase: subscribe to a topic, await messages, embed + upsert into the store. The only moving part is the optional `bus` injection into `WriterAgent` (D008), which is the same optional-dependency pattern already used by `set_sampling_client`.

Two files need to be created (`knowledge/ingest.py`, `tests/test_ingest.py`) and one file needs a small addition (`agents/writer.py` — publish to `agent.output.final` when `bus` is set). The regression target is `tests/test_pipeline.py` — existing `WriterAgent` tests pass `WriterAgent()` with no bus argument and must keep passing.

## Recommendation

Build in order:
1. `knowledge/ingest.py` — `IngestionWorker` class; accepts `bus`, `store`, `embedder`; subscribes to `agent.output.final`; chunks report text; embeds + upserts with `owner_id` from message content.
2. Modify `agents/writer.py` — add optional `bus: MessageBus | None = None` to `__init__`; publish after report generation.
3. `tests/test_ingest.py` — unit tests; `tests/test_pipeline.py` regression check.

No new dependencies needed. All building blocks exist.

## Implementation Landscape

### Key Files

- `src/mcp_agent_factory/knowledge/ingest.py` — **NEW**: `IngestionWorker`; `__init__(self, bus, store, embedder, owner_id)`; `async start()` subscribes to `agent.output.final` and loops; `async _process(msg)` chunks text → embeds → upserts.
- `src/mcp_agent_factory/knowledge/vector_store.py` — `InMemoryVectorStore.upsert(owner_id, text, vector)` — already accepts these args; no changes needed.
- `src/mcp_agent_factory/knowledge/embedder.py` — `StubEmbedder.embed(text) -> np.ndarray` — already works; no changes needed.
- `src/mcp_agent_factory/agents/writer.py` — `WriterAgent.run()` needs optional bus injection. Add `__init__(self, bus=None)` and `self._bus = bus`; after `ReportResult` is constructed, if `self._bus` is set, call `self._bus.publish("agent.output.final", AgentMessage(...))` with `content={"text": report_text, "owner_id": owner_id, "session_key": analysis.session_key}`. The `owner_id` must come from the caller — add as optional param to `run()` defaulting to `""` (or require it; tests pass `""` via default).
- `src/mcp_agent_factory/messaging/bus.py` — `MessageBus`, `AgentMessage` — no changes needed; already supports fire-and-forget `publish`.
- `tests/test_ingest.py` — **NEW**: tests for `IngestionWorker`.
- `tests/test_pipeline.py` — **regression**: all existing tests must continue to pass; `WriterAgent()` called with no args must still work.

### Message Schema for `agent.output.final`

```python
AgentMessage(
    topic="agent.output.final",
    sender="writer-agent",
    content={
        "text": report_text,        # full report string
        "owner_id": owner_id,       # str, from JWT sub or test fixture
        "session_key": session_key, # str, for traceability
    }
)
```

`IngestionWorker._process(msg)` reads `msg.content["text"]` and `msg.content["owner_id"]`. Chunking strategy: split on double-newlines (`\n\n`), strip whitespace, filter empty strings. Each chunk is embedded and upserted separately.

### WriterAgent change (D008 pattern)

```python
class WriterAgent:
    def __init__(self, bus=None):
        self._bus = bus

    async def run(self, analysis, ctx, owner_id=""):
        ...  # existing logic unchanged
        if self._bus is not None:
            from mcp_agent_factory.messaging.bus import AgentMessage
            self._bus.publish("agent.output.final", AgentMessage(
                topic="agent.output.final",
                sender="writer-agent",
                content={"text": report_text, "owner_id": owner_id, "session_key": analysis.session_key},
            ))
        return ReportResult(...)
```

Existing tests call `WriterAgent()` and `await agent.run(analysis, ctx)` — both default to `None`/`""` so are completely unaffected.

### Build Order

1. **`knowledge/ingest.py`** first — pure new file, no risk of breaking anything.
2. **`agents/writer.py`** second — tiny addition; verify `test_pipeline.py` still passes immediately after.
3. **`tests/test_ingest.py`** last — integration test exercising the full ingest path end-to-end.

### Verification Approach

```bash
PYTHONPATH=src pytest tests/test_ingest.py -v      # new tests pass
PYTHONPATH=src pytest tests/test_pipeline.py -v    # no regressions
PYTHONPATH=src pytest tests/ -v                    # full suite green
```

Test cases for `test_ingest.py`:
- `test_worker_ingests_message` — publish to `agent.output.final`, call `_process` directly or drive a single loop iteration, assert `store.search(owner_id, ...)` returns non-empty.
- `test_worker_chunks_text` — multi-paragraph report → multiple chunks upserted (search returns multiple results).
- `test_worker_owner_isolation` — upsert via worker for `owner_id='alice'`, search for `owner_id='bob'` → empty (re-uses R101 invariant).
- `test_worker_ignores_empty_chunks` — report with blank lines → no crash, only non-empty chunks stored.
- `test_writer_publishes_on_bus_when_set` — `WriterAgent(bus=bus)`, call `run(analysis, ctx, owner_id='u1')`, assert `queue.get_nowait()` delivers the `agent.output.final` message.
- `test_writer_no_publish_when_bus_none` — `WriterAgent()` (no bus), run succeeds, no exception.

## Constraints

- Tab indentation throughout (project convention).
- No new pip dependencies — `asyncio.Queue` and numpy are already available.
- `IngestionWorker.start()` must be fire-and-forget (non-blocking). Use `asyncio.ensure_future` or wrap in a task from the caller; the worker itself loops with `await queue.get()`.
- `owner_id` in the message content is the sole source of namespace — never hardcode.

## Common Pitfalls

- **`run()` signature change breaking existing tests** — existing `test_pipeline.py` calls `WriterAgent().run(analysis, ctx)` with no `owner_id`. Default `owner_id=""` prevents breakage. Do not make it a required positional argument.
- **Worker blocking on empty queue** — `start()` should loop until cancelled; use `asyncio.CancelledError` handling so tests can stop the worker cleanly. A simpler test-friendly approach: expose `_process(msg)` as a public method so tests can drive it synchronously without spinning up the full loop.
- **Chunking empty strings** — `"\n\n".join(...)` on a report that starts/ends with blank lines produces empty-string chunks. Filter with `[c for c in chunks if c.strip()]`.
