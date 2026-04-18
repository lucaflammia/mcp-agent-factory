---
id: S03
parent: M007
provides:
  - src/mcp_agent_factory/streams/redlock.py — RedlockClient with N-node quorum acquire/release
  - RedlockClient exported from mcp_agent_factory.streams
  - tests/test_m007_redlock.py — 3 integration tests (quorum, contention, release)
key_files:
  - src/mcp_agent_factory/streams/redlock.py
  - src/mcp_agent_factory/streams/__init__.py
  - tests/test_m007_redlock.py
key_decisions:
  - Lock token is uuid4().hex per acquire call — safe release without releasing another client's lock
  - quorum = len(nodes) // 2 + 1 — works for any odd number of nodes
  - _release_partial used for both failure cleanup and final release — single code path
  - retry_count=1 in contention test — avoids waiting through retries during test
verification_result: pass (requires live 3-node Redis)
completed_at: 2026-04-18T00:00:00Z
---

# S03: Redlock 3-Node Quorum

**RedlockClient implemented with quorum acquire/release across N independent Redis nodes — supersedes single-node DistributedLock from M006.**

## What Happened

T01 implemented `src/mcp_agent_factory/streams/redlock.py`. `RedlockClient` takes a list of Redis clients (any length), computes quorum as `len(nodes)//2+1`, and for each acquire attempt: generates a UUID token, issues `SET key token NX PX ttl_ms` on each node, counts successes, returns True only if quorum reached within TTL. On failure, releases partial locks via `_release_partial`. Release uses the stored token to safely DEL only keys we own.

T02 wrote three integration tests: `test_redlock_acquires_quorum` (acquire → release → re-acquire), `test_redlock_contention_serialises` (two clients race, exactly one wins), `test_redlock_releases_on_all_nodes` (GET on all 3 nodes returns None after release). `autouse` fixture cleans `test:lock:*` keys from all nodes after each test.

## Deviations

None.

## Files Created/Modified

- `src/mcp_agent_factory/streams/redlock.py` — RedlockClient implementation
- `src/mcp_agent_factory/streams/__init__.py` — RedlockClient exported
- `tests/test_m007_redlock.py` — 3 integration tests
