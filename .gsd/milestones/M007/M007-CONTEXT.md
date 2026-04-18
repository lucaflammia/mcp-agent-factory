# M007: Real Infrastructure — Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

## Implementation Decisions

- **Docker Compose is the test harness** — all integration tests run against `docker-compose up`; the existing unit test suite must continue to pass without Docker (fakes stay in place)
- **pytest marker gate** — integration tests use `@pytest.mark.integration`; `conftest_integration.py` fixtures skip automatically when the live stack is not reachable (connection refused → pytest.skip)
- **aiokafka goes in `[project.optional-dependencies] infra`** — not a mandatory dep; existing `kafka_adapter.py` guard (`try/except ImportError`) already handles absence cleanly
- **RedlockClient implements the existing `DistributedLock` protocol** — same interface as M006's single-node SET NX implementation; `StreamWorker` can swap in RedlockClient without code changes (supersedes D010)
- **3-node Redis cluster is 3 standalone Redis instances** — not Redis Cluster (which requires special client); Redlock only needs 3 independent nodes, not a Redis Cluster topology
- **`StreamWorker` is already stateless** — no source changes needed for R016; the multi-process test harness uses `multiprocessing.Process` to spawn 2 workers and a shared `fakeredis` server (or real Redis in integration mode)
- **Zookeeper required for Kafka** — use `confluentinc/cp-zookeeper` + `confluentinc/cp-kafka` images; they're the most reliable for local dev

## Agent's Discretion

- Port assignments: redis=6379, redis-node-{1,2,3}=638{1,2,3}, kafka=9092, zookeeper=2181
- Redlock TTL defaults: 5000ms lock TTL, 3 retry attempts with 50ms backoff
- Integration test topic names: `m007.test.events`, `m007.tasks.search`, `m007.tasks.write`
- `conftest_integration.py` lives in `tests/` alongside existing `conftest.py`

## Deferred Ideas

- KafkaEventLog consumer group offset management (full consumer group rebalancing) — R019 (already out of scope)
- Redis Sentinel or Redis Cluster topology — out of scope; 3 standalone nodes are sufficient for Redlock
- Persistent Kafka topic retention / compaction — not needed for tests
