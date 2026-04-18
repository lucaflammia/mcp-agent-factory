# T02: test_m007_redlock.py — quorum, contention, release

**Slice:** S03
**Milestone:** M007

## Goal

Write integration tests for `RedlockClient` covering the three core Redlock scenarios: successful quorum acquire, contention serialisation, and clean release.

## Must-Haves

### Truths
- `test_redlock_acquires_quorum`: fresh key, first acquire returns `True`; after release, second acquire returns `True`
- `test_redlock_contention_serialises`: two clients race for same key; exactly one returns `True`, the other returns `False`
- `test_redlock_releases_on_all_nodes`: after `release()`, `GET key` on all 3 nodes returns `None`

### Artifacts
- `tests/test_m007_redlock.py` — min 60 lines, 3 test functions, all `@pytest.mark.integration`

### Key Links
- Imports `RedlockClient` from `mcp_agent_factory.streams.redlock`
- Uses `real_redis_cluster` fixture (list of 3 Redis clients) from `conftest_integration.py`

## Steps

1. Write `test_redlock_acquires_quorum(real_redis_cluster)`: create `RedlockClient(real_redis_cluster)`, acquire `"test:lock:quorum"`, assert True; release; acquire again, assert True
2. Write `test_redlock_contention_serialises(real_redis_cluster)`: create two clients with same nodes; both call `acquire("test:lock:contention")`; assert exactly one True and one False
3. Write `test_redlock_releases_on_all_nodes(real_redis_cluster)`: acquire `"test:lock:release"`; release; for each node `assert node.get("test:lock:release") is None`
4. Add unique key suffix per test (use `uuid.uuid4().hex[:8]`) to prevent inter-test pollution
5. Mark all tests `@pytest.mark.integration`

## Context
- Contention test doesn't require threads — sequential calls suffice: if first acquire holds the lock, second fails immediately
- Key cleanup: `@pytest.fixture(autouse=True)` that DELs test keys from all nodes after each test is cleaner than per-test cleanup
