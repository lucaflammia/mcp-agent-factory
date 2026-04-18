# S01: Docker Compose Stack (Redis + Kafka)

**Goal:** Provide a reproducible local infrastructure stack and pytest fixture layer that integration tests in S02–S04 build on. The unit test suite must continue to pass without Docker.

**Demo:** `docker-compose up -d` starts 5 services (redis, redis-node-1/2/3, kafka+zookeeper). `pytest -m integration --co` lists integration test placeholders without errors. `pytest` (no marker) passes unmodified — 246 tests green.

## Must-Haves

- `docker-compose.yml` at repo root defines: `redis` (6379), `redis-node-1` (6381), `redis-node-2` (6382), `redis-node-3` (6383), `zookeeper` (2181), `kafka` (9092)
- `tests/conftest_integration.py` exports `real_redis`, `real_redis_cluster` (list of 3 clients), `real_kafka_bootstrap` (str) fixtures — each skips if connection refused
- `pyproject.toml` gains `[project.optional-dependencies] infra = ["aiokafka>=0.10", "redis>=5"]`
- `pytest.ini` (or `pyproject.toml [tool.pytest.ini_options]`) registers the `integration` marker so `-m integration` doesn't warn
- All 246 existing tests still pass (`pytest --ignore=tests/conftest_integration.py` or just `pytest` — conftest_integration fixtures only activate when called)

## Tasks

- [ ] **T01: docker-compose.yml + pyproject.toml infra deps**
  Write the Compose file with all 6 services and add aiokafka + redis to optional infra deps.

- [ ] **T02: conftest_integration.py + pytest marker registration**
  Write the pytest fixtures with skip-on-no-docker guards and register the `integration` marker.

## Files Likely Touched

- `docker-compose.yml` (new)
- `pyproject.toml`
- `tests/conftest_integration.py` (new)
