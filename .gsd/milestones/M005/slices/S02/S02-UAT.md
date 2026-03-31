# S02: Async Ingestion Worker — UAT

**Milestone:** M005
**Written:** 2026-03-31T07:26:53.375Z

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: all behaviour is tested by the pytest suite; no runtime server needed for ingestion worker verification.

## Preconditions

- Python 3.11 with dependencies installed (`pip install -e ".[dev]"`)
- `PYTHONPATH=src` set for all commands

## Smoke Test

```bash
PYTHONPATH=src python -c "from mcp_agent_factory.knowledge.ingest import IngestionWorker; from mcp_agent_factory.agents.writer import WriterAgent; print('imports ok')"
```
Expected: prints `imports ok` with exit code 0.

## Test Cases

### 1. Worker ingests a message and stores chunk

```bash
PYTHONPATH=src pytest tests/test_ingest.py::TestIngestionWorker::test_process_chunks_and_upserts -v
```
**Expected:** PASSED — store.search returns the upserted chunk after _process is called.

### 2. Worker splits on double-newline and filters empties

```bash
PYTHONPATH=src pytest tests/test_ingest.py::TestIngestionWorker::test_process_filters_empty_chunks -v
```
**Expected:** PASSED — only non-empty paragraphs are stored; blank lines between paragraphs produce no extra chunks.

### 3. Cross-tenant isolation

```bash
PYTHONPATH=src pytest tests/test_ingest.py::TestIngestionWorker::test_multiple_owners_isolated -v
```
**Expected:** PASSED — upsert for owner_id='alice', search for owner_id='bob' → empty list.

### 4. start() loop processes a real bus-published message

```bash
PYTHONPATH=src pytest tests/test_ingest.py::TestIngestionWorker::test_start_processes_published_message -v
```
**Expected:** PASSED — message published to bus is consumed and stored by the running worker task.

### 5. WriterAgent publishes to bus when bus is set

```bash
PYTHONPATH=src pytest tests/test_ingest.py::TestWriterAgentBusIntegration::test_writer_publishes_to_bus_when_bus_provided -v
```
**Expected:** PASSED — queue.get_nowait() returns AgentMessage with content["owner_id"] == 'u1'.

### 6. WriterAgent works without bus (no regression)

```bash
PYTHONPATH=src pytest tests/test_ingest.py::TestWriterAgentBusIntegration::test_writer_no_publish_without_bus -v
```
**Expected:** PASSED — no exception; WriterAgent.run() returns report text normally.

### 7. Full pipeline regression check

```bash
PYTHONPATH=src pytest tests/test_pipeline.py -v
```
**Expected:** 20/20 PASSED — no regressions in existing multi-agent pipeline tests.

### 8. Full suite

```bash
PYTHONPATH=src pytest tests/ -v
```
**Expected:** 199/199 PASSED.

## Edge Cases

### CancelledError stops start() cleanly

```bash
PYTHONPATH=src pytest tests/test_ingest.py::TestIngestionWorker::test_start_handles_cancelled_error_cleanly -v
```
**Expected:** PASSED — cancelling the worker task does not raise; the loop exits gracefully.

### Backward compatibility — no owner_id arg

```bash
PYTHONPATH=src pytest tests/test_ingest.py::TestWriterAgentBusIntegration::test_writer_backward_compat_no_owner_id -v
```
**Expected:** PASSED — calling WriterAgent(bus=bus).run(analysis, ctx) without owner_id defaults to '' and publishes correctly.

## Failure Signals

- Any test failure in `tests/test_ingest.py` indicates ingestion worker or WriterAgent bus integration is broken.
- Any regression in `tests/test_pipeline.py` indicates WriterAgent backward-compat was broken.
- ImportError on `IngestionWorker` or `WriterAgent` indicates module wiring issue in `knowledge/__init__.py`.

## Not Proven By This UAT

- Live async throughput / back-pressure behaviour under load
- IngestionWorker.start() lifecycle management (external caller must create_task)
- Integration with real sentence-transformer embeddings (StubEmbedder used throughout)

## Notes for Tester

All tests are deterministic and hermetic — no network, no external services. StubEmbedder uses random vectors; search results are consistent within a test run but not across runs.
