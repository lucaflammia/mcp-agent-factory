# S02: Real Kafka EventLog Integration

**Goal:** Exercise `KafkaEventLog` against a real Kafka broker using the fixtures from S01. No source changes needed — `kafka_adapter.py` already implements the `EventLog` protocol; tests just need to call it with a live broker.

**Demo:** `pytest -m integration tests/test_m007_kafka.py -v` passes — events appended to Kafka are readable back; two different session topics are independent; the `EventLog` protocol contract holds with a real broker.

## Must-Haves

- `KafkaEventLog.append()` returns a string offset for each published event
- `KafkaEventLog.read()` returns the same events in order
- Two calls with different topic names go to independent topics (no cross-contamination)
- Tests are marked `@pytest.mark.integration` and use the `real_kafka_bootstrap` fixture
- Tests skip cleanly when Kafka is not running

## Tasks

- [ ] **T01: test_m007_kafka.py — append + read + topic isolation**
  Write integration tests exercising KafkaEventLog against real Kafka.

## Files Likely Touched

- `tests/test_m007_kafka.py` (new)
