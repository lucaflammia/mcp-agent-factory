# S04: Multi-Instance StreamWorker

**Goal:** Prove R016 — that `StreamWorker` is truly stateless and two OS-level processes sharing a consumer group each claim and process distinct tasks with no double-execution. Uses `multiprocessing` against real Redis.

**Demo:** `pytest -m integration tests/test_m007_scaling.py -v` passes — 10 tasks published; 2 worker processes each consume some; total consumed == 10 with no duplicates. PEL recovery test: one worker crashes mid-task; second worker reclaims and processes the stuck message.

## Must-Haves

- Two `multiprocessing.Process` workers, both using the same stream + consumer group on real Redis
- After both workers drain the stream, the union of their results == all published tasks (no gaps)
- No task appears in both workers' results (no duplicates)
- PEL recovery: worker A claims a task but exits without ACKing; worker B calls `recover()` and processes it
- Tests marked `@pytest.mark.integration`, using `real_redis` fixture

## Tasks

- [ ] **T01: test_m007_scaling.py — no-duplicate + PEL recovery across processes**
  Write multi-process integration tests for StreamWorker horizontal scaling.

## Files Likely Touched

- `tests/test_m007_scaling.py` (new)
