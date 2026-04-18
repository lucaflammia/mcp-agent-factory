# T01: test_m007_scaling.py — no-duplicate + PEL recovery across processes

**Slice:** S04
**Milestone:** M007

## Goal

Write multi-process integration tests that exercise `StreamWorker` horizontal scaling against real Redis. Two worker processes share a consumer group — prove no double-execution. A separate test proves PEL recovery when one worker crashes.

## Must-Haves

### Truths
- `test_two_workers_no_double_execution`: 10 tasks published; 2 worker processes run concurrently; combined claimed task IDs == all 10 task IDs; intersection (duplicates) == empty
- `test_pel_recovery_across_processes`: worker A claims a task, exits without ACKing; worker B's `recover()` returns that task; worker B ACKs it; PEL is empty after recovery

### Artifacts
- `tests/test_m007_scaling.py` — min 80 lines, 2 test functions, both `@pytest.mark.integration`

### Key Links
- `test_m007_scaling.py` → `StreamWorker` from `mcp_agent_factory.streams.worker`
- `test_m007_scaling.py` → `real_redis` fixture from `conftest_integration.py`
- `test_m007_scaling.py` → `AgentTask` from `mcp_agent_factory.agents.models`

## Steps

1. Write a `_worker_process(host, port, stream, group, consumer_name, result_queue)` function — creates its own `redis.Redis(host, port)`, creates `StreamWorker`, loops calling `claim_one()` until None, ACKs each, puts task IDs into a `multiprocessing.Queue`
2. Write `test_two_workers_no_double_execution(real_redis)`: publish 10 `AgentTask` objects; spawn 2 processes with `_worker_process`; join both; collect results; assert `set(w1_ids) | set(w2_ids) == all_ids` and `set(w1_ids) & set(w2_ids) == set()`
3. Write `test_pel_recovery_across_processes(real_redis)`: publish 1 task; worker A claims but exits without ACKing (process just exits); sleep 100ms; worker B calls `recover(min_idle_ms=50, new_consumer="worker-b")`; assert recovered list has the task; worker B ACKs; assert `xpending_range` returns empty
4. Add stream/group name per test using `uuid.uuid4().hex[:8]` suffix to isolate tests
5. Mark both `@pytest.mark.integration`

## Context
- `multiprocessing.Queue` is the cleanest IPC for collecting results from worker subprocesses
- `_worker_process` must be a module-level function (not nested) for `multiprocessing` to pickle it on Linux
- Worker processes must use real Redis (port 6379 from `real_redis` fixture) — pass host/port explicitly, not the client object (not picklable)
- PEL idle time: use `min_idle_ms=50` and `time.sleep(0.1)` before recovery to ensure the entry is actually idle
