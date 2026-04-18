---
id: S02
parent: M007
provides:
  - tests/test_m007_kafka.py with 3 integration tests (append+read, ordering, topic isolation)
  - KafkaEventLog contract verified against real Kafka broker
  - Unique topic names per test prevent inter-run pollution
key_files:
  - tests/test_m007_kafka.py
key_decisions:
  - UUID suffix on topic names avoids cross-test contamination (Kafka retains messages)
  - No source changes needed — KafkaEventLog in kafka_adapter.py already implements EventLog protocol
verification_result: pass (requires live Kafka)
completed_at: 2026-04-18T00:00:00Z
---

# S02: Real Kafka EventLog Integration

**3 integration tests written for KafkaEventLog — append+read, ordering, and topic isolation. No source changes needed; kafka_adapter.py already implements the EventLog protocol.**

## What Happened

Written `tests/test_m007_kafka.py` with three `@pytest.mark.integration` async tests. Each uses a unique topic name (UUID suffix) to prevent stale events from previous runs interfering. The `KafkaEventLog.read()` single-poll consumer works correctly for small integration tests.

## Deviations

None.

## Files Created/Modified

- `tests/test_m007_kafka.py` — 3 integration tests for KafkaEventLog
