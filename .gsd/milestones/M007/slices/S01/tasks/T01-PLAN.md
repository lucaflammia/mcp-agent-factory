# T01: docker-compose.yml + pyproject.toml infra deps

**Slice:** S01
**Milestone:** M007

## Goal

Write `docker-compose.yml` at the repo root with 6 services covering standalone Redis, 3 independent Redis nodes (for Redlock), and Kafka+Zookeeper. Add `aiokafka` and `redis` to `pyproject.toml` optional-dependencies.

## Must-Haves

### Truths
- `docker-compose config` exits 0 (valid YAML, all images resolvable by name)
- Services defined: `redis` (port 6379), `redis-node-1` (6381), `redis-node-2` (6382), `redis-node-3` (6383), `zookeeper` (2181), `kafka` (9092)
- `kafka` service has `KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092` so clients on the host can connect
- `pyproject.toml` `[project.optional-dependencies]` has `infra = ["aiokafka>=0.10", "redis>=5"]`

### Artifacts
- `docker-compose.yml` — root of repo, min 30 lines, all 6 services present
- `pyproject.toml` — `infra` extra present with aiokafka and redis

### Key Links
- `conftest_integration.py` (T02) will read the same ports defined here — ports must match

## Steps

1. Write `docker-compose.yml` with `version: "3.9"`, services: `redis`, `redis-node-1`, `redis-node-2`, `redis-node-3`, `zookeeper`, `kafka`
2. Use images: `redis:7-alpine` for all Redis nodes, `confluentinc/cp-zookeeper:7.5.0`, `confluentinc/cp-kafka:7.5.0`
3. Set Kafka env vars: `KAFKA_BROKER_ID`, `KAFKA_ZOOKEEPER_CONNECT`, `KAFKA_ADVERTISED_LISTENERS`, `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1`
4. Add health checks to redis and kafka services (`redis-cli ping`, `kafka-topics.sh --list`)
5. Add `infra` extra to `pyproject.toml`

## Context
- `kafka_adapter.py` already has `try/except ImportError` guard for aiokafka — adding to optional deps keeps the package importable without the extra installed
- redis-py is already used in `streams/worker.py`; adding to `infra` extra makes it explicit for production installs
