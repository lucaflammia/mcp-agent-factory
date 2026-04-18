# T01: test_m007_kafka.py — append + read + topic isolation

**Slice:** S02
**Milestone:** M007

## Goal

Write integration tests for `KafkaEventLog` that run against a real Kafka broker. Three test cases: basic append+read, ordering guarantee across multiple appends, and topic isolation between two independent topics.

## Must-Haves

### Truths
- `test_kafka_append_read`: appends one event, reads it back, event dict matches
- `test_kafka_ordering`: appends 3 events, reads all 3, they come back in append order
- `test_kafka_topic_isolation`: appends to `m007.tasks.search` and `m007.tasks.write`; reading `m007.tasks.search` returns only the search event

### Artifacts
- `tests/test_m007_kafka.py` — min 50 lines, 3 test functions, all marked `@pytest.mark.integration`

### Key Links
- `test_m007_kafka.py` → `KafkaEventLog` via `from mcp_agent_factory.streams.kafka_adapter import KafkaEventLog`
- `test_m007_kafka.py` → `real_kafka_bootstrap` fixture from `conftest_integration.py`

## Steps

1. Import `KafkaEventLog`, `pytest`, `pytest_asyncio` fixtures
2. Write `async def test_kafka_append_read(real_kafka_bootstrap)` — start log, append `{"task_id": "t1"}` to topic `m007.test.events`, read back, assert event present, stop log
3. Write `async def test_kafka_ordering(real_kafka_bootstrap)` — append 3 events with sequence numbers, read all, assert order
4. Write `async def test_kafka_topic_isolation(real_kafka_bootstrap)` — append to two different topics, read each, assert no cross-contamination
5. Add unique topic name suffix (timestamp or uuid) to each test to avoid inter-test pollution

## Context
- `KafkaEventLog.read()` uses a simple single-poll consumer that reads until no more messages — works for small integration tests
- Use `@pytest.mark.asyncio` on each test (pytest-asyncio already in dev deps)
- Unique topic names per test are critical — Kafka retains messages; a rerun without unique names will see stale events
