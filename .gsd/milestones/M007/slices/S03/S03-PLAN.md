# S03: Redlock 3-Node Quorum

**Goal:** Implement `RedlockClient` — a `DistributedLock` protocol implementation that acquires a lock across 3 independent Redis nodes using the Redlock algorithm (quorum = 2/3). Supersedes the single-node SET NX from M006.

**Demo:** `pytest -m integration tests/test_m007_redlock.py -v` passes — lock acquired when 2+/3 nodes respond; contention between two clients serialises correctly; lock releases on all 3 nodes.

## Must-Haves

- `RedlockClient` lives in `src/mcp_agent_factory/streams/redlock.py`
- Implements the same `DistributedLock` protocol as M006's single-node implementation (acquire/release interface)
- Acquire: SET NX EX on all 3 nodes, count successes; succeed only if ≥ 2 (quorum); release all on failure
- Release: DEL the key on all 3 nodes (best-effort; no exception on miss)
- Contention test: two `RedlockClient` instances racing for the same key — exactly one wins, the other gets `False`
- Tests marked `@pytest.mark.integration`, using `real_redis_cluster` fixture

## Tasks

- [ ] **T01: RedlockClient implementation**
  Implement `src/mcp_agent_factory/streams/redlock.py` with quorum acquire/release.

- [ ] **T02: test_m007_redlock.py — quorum, contention, release**
  Write integration tests covering the 3 core scenarios.

## Files Likely Touched

- `src/mcp_agent_factory/streams/redlock.py` (new)
- `src/mcp_agent_factory/streams/__init__.py`
- `tests/test_m007_redlock.py` (new)
