# T01: RedlockClient implementation

**Slice:** S03
**Milestone:** M007

## Goal

Implement `RedlockClient` in `src/mcp_agent_factory/streams/redlock.py`. It takes a list of Redis clients (one per node) and implements acquire/release using the Redlock quorum algorithm.

## Must-Haves

### Truths
- `client.acquire(key, ttl_ms)` returns `True` when ≥ 2/3 nodes SET NX succeed within the TTL window
- `client.acquire(key, ttl_ms)` returns `False` and releases all partial locks when < 2 nodes respond
- `client.release(key)` issues DEL on all 3 nodes; does not raise if key already gone
- A second `RedlockClient` calling `acquire` on the same key while first holds the lock returns `False`

### Artifacts
- `src/mcp_agent_factory/streams/redlock.py` — min 60 lines, exports `RedlockClient`
- `src/mcp_agent_factory/streams/__init__.py` — `RedlockClient` importable from `mcp_agent_factory.streams`

### Key Links
- `RedlockClient` must be usable as a `DistributedLock` (same acquire/release signature as M006's `IdempotencyGuard`)
- `test_m007_redlock.py` (T02) imports `RedlockClient` from `mcp_agent_factory.streams.redlock`

## Steps

1. Read `src/mcp_agent_factory/streams/idempotency.py` to confirm the `DistributedLock` protocol interface
2. Write `RedlockClient.__init__(self, nodes: list[redis.Redis], ttl_ms: int = 5000, retry_count: int = 3, retry_delay_ms: int = 50)`
3. Implement `acquire(self, key: str) -> bool`: generate a random token; for each node try `SET key token NX PX ttl_ms`; count successes; if < quorum, release partial and return False
4. Implement `release(self, key: str) -> None`: for each node, check value matches token then DEL (use pipeline for atomicity); swallow `ResponseError`
5. Export from `streams/__init__.py`

## Context
- The lock token (random UUID) is critical for safe release — without it, a delayed client could release another client's lock
- Use `uuid.uuid4().hex` as the token; store as instance variable per acquire call
- Quorum = `len(nodes) // 2 + 1` — works for any odd number of nodes
