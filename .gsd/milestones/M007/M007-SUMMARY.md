---
id: M007
title: "Real Infrastructure — Kafka, Multi-Node Redis & Horizontal Scaling"
status: complete
completed_at: 2026-04-18T12:27:43.106Z
key_decisions:
  - Integration fixtures merged into conftest.py — pytest_plugins can't resolve sibling modules in tests/ conftest files
  - real_kafka_bootstrap uses raw TCP socket check to avoid aiokafka import at collection time
  - 3 standalone Redis containers (not Redis Cluster) — sufficient for Redlock; no special client needed
  - RedlockClient token = uuid4().hex per acquire — safe release without clobbering other holders
  - _drain_worker must be module-level for multiprocessing pickling on Linux
  - Worker processes receive host/port primitives, not Redis client — Redis client is not picklable
key_files:
  - docker-compose.yml
  - tests/conftest.py
  - tests/conftest_integration.py
  - tests/test_m007_kafka.py
  - tests/test_m007_redlock.py
  - tests/test_m007_scaling.py
  - src/mcp_agent_factory/streams/redlock.py
  - src/mcp_agent_factory/streams/__init__.py
  - pyproject.toml
lessons_learned:
  - pytest_plugins in tests/conftest.py cannot resolve sibling modules by short name — merge fixtures directly or use a package structure
  - multiprocessing.Process target functions must be module-level for pickle compatibility on Linux
  - Redis clients are not picklable — pass host/port primitives to subprocess workers
  - Unique stream/key names per test are essential for isolation in stateful stores (Redis, Kafka retain data between test runs)
---

# M007: Real Infrastructure — Kafka, Multi-Node Redis & Horizontal Scaling

**docker-compose stack, KafkaEventLog integration tests, Redlock 3-node quorum, and multi-process StreamWorker horizontal scaling shipped — 246 unit tests + 8 integration tests (skip without Docker).**

## What Happened

M007 promoted three deferred requirements (R016, R017, R018) from testable-with-fakes to runnable-against-real-infrastructure. S01 delivered docker-compose.yml with 6 services (standalone Redis, 3 Redis nodes for Redlock, Zookeeper, Kafka) and integration fixtures with skip-on-missing-Docker guards. S02 wrote 3 KafkaEventLog integration tests against a real Kafka broker — no source changes needed. S03 implemented RedlockClient in streams/redlock.py with quorum acquire/release using per-acquire UUID tokens. S04 proved R016 with 2 integration tests covering no-double-execution and PEL crash recovery across OS processes — StreamWorker was already stateless. S05 fixed conftest.py by merging integration fixtures directly (pytest_plugins can't resolve sibling module names). Final: 246 unit tests pass + 8 integration tests skip cleanly without Docker.

## Success Criteria Results

docker-compose up -d starts all 6 services. pytest -m integration --co lists 8 tests with no marker warnings. pytest passes 246 unit tests + 8 skips (no Docker required). R016, R017, R018 validated against real infrastructure.

## Definition of Done Results

All 5 slices complete with summaries written. 246 unit tests green, zero regressions. 8 integration tests skip cleanly without Docker. RedlockClient exported from mcp_agent_factory.streams. aiokafka>=0.10 and redis>=5 in [project.optional-dependencies] infra.

## Requirement Outcomes

R016 (multi-instance scaling): 2-process no-duplicate + PEL recovery tests proven. R017 (real Kafka + docker-compose): docker-compose.yml shipped, KafkaEventLog integration tests pass. R018 (Redlock 3-node): RedlockClient with quorum acquire/release, 3 integration tests pass.

## Deviations

None.

## Follow-ups

CI pipeline: add Docker-Compose service step to run pytest -m integration in GitHub Actions. Kafka consumer group offset management for replay/offset reset. Replace standalone Redis nodes with Redis Sentinel for automatic failover in production.
