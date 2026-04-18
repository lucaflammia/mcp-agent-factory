# S02 UAT: Real Kafka EventLog

## Test When Ready (requires docker-compose up -d kafka)

1. `pytest -m integration tests/test_m007_kafka.py -v` → 3 passed
2. Confirm each test name visible: `test_kafka_append_read`, `test_kafka_ordering`, `test_kafka_topic_isolation`
