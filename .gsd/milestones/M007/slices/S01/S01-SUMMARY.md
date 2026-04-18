---
id: S01
parent: M007
provides:
  - docker-compose.yml with 6 services (redis, redis-node-{1,2,3}, zookeeper, kafka)
  - tests/conftest_integration.py with real_redis, real_redis_cluster, real_kafka_bootstrap fixtures
  - Integration tests skip cleanly when Docker stack is not running
  - pytest integration marker registered in pyproject.toml
  - aiokafka>=0.10 and redis>=5 added as [project.optional-dependencies] infra
key_files:
  - docker-compose.yml
  - tests/conftest_integration.py
  - pyproject.toml
key_decisions:
  - real_kafka_bootstrap uses raw TCP socket check — avoids importing aiokafka at collection time
  - 3 standalone Redis containers (not Redis Cluster) — Redlock only needs independent nodes
  - conftest_integration.py is separate from conftest.py — keeps existing fixture namespace clean
verification_result: pass
completed_at: 2026-04-18T00:00:00Z
---

# S01: Docker Compose Stack (Redis + Kafka)

**docker-compose.yml, integration fixtures, and pytest marker wired — 246 unit tests still green, `pytest -m integration --co` collects cleanly with no warnings.**

## What Happened

T01 wrote `docker-compose.yml` with 6 services: standalone `redis:7-alpine` on 6379, three independent Redis nodes on 6381–6383 (for Redlock), `confluentinc/cp-zookeeper:7.5.0` on 2181, and `confluentinc/cp-kafka:7.5.0` on 9092. Kafka env vars include `KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092` for host connectivity and `KAFKA_AUTO_CREATE_TOPICS_ENABLE=true` so integration tests don't need to pre-create topics. Health checks on all services.

T02 wrote `tests/conftest_integration.py` with three fixtures: `real_redis` (port 6379), `real_redis_cluster` (list of 3 clients on 6381–6383), `real_kafka_bootstrap` (TCP socket check, returns `"localhost:9092"`). All skip gracefully on `ConnectionRefusedError`. The `integration` marker was registered in `pyproject.toml [tool.pytest.ini_options]` to eliminate marker warnings.

## Deviations

`real_kafka_bootstrap` uses a raw TCP socket check instead of an `aiokafka` producer ping — avoids the async complexity and the import-time dependency on aiokafka being installed.

## Files Created/Modified

- `docker-compose.yml` — 6-service stack definition
- `tests/conftest_integration.py` — real_redis, real_redis_cluster, real_kafka_bootstrap fixtures
- `pyproject.toml` — infra optional-deps + integration marker
