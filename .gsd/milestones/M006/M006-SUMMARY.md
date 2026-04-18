---
id: M006
title: "Redis Streams, EventLog, Validation Gate, Idempotency & Circuit Breakers"
status: complete
completed_at: 2026-04-18T12:27:20.462Z
key_decisions:
  - StreamWorker and MessageBus coexist — MessageBus handles in-process SSE fan-out, StreamWorker handles cross-process task intake
  - Single-node SET NX EX locking behind DistributedLock protocol
  - EventLog Protocol + InProcessEventLog pattern for test-time broker-free operation
  - DistributedLock keys must use a namespace prefix (lock:) to avoid SET NX collision with IdempotencyGuard keys in shared Redis
key_files:
  - src/mcp_agent_factory/streams/worker.py
  - src/mcp_agent_factory/streams/eventlog.py
  - src/mcp_agent_factory/streams/kafka_adapter.py
  - src/mcp_agent_factory/streams/idempotency.py
  - src/mcp_agent_factory/streams/circuit_breaker.py
  - src/mcp_agent_factory/gateway/validation.py
  - src/mcp_agent_factory/gateway/service_layer.py
  - tests/test_m006_streams.py
  - tests/test_m006_eventlog.py
  - tests/test_m006_gateway.py
  - tests/test_m006_reliability.py
  - tests/test_m006_integration.py
lessons_learned:
  - DistributedLock and IdempotencyGuard both use SET NX on the same Redis — always namespace lock keys with a prefix to prevent collision
  - Module-level singletons capture dependency references at construction time; test injection helpers must also patch the singleton's attributes
  - InProcessEventLog.read returns (msg_id, event) tuples — document this clearly for test authors
---

# M006: Redis Streams, EventLog, Validation Gate, Idempotency & Circuit Breakers

**Redis Streams, EventLog, ValidationGate, IdempotencyGuard, and CircuitBreaker all shipped and integrated — 231 tests green, R001–R015 validated.**

## What Happened

M006 delivered Redis Streams consumer groups (S01), Kafka-protocol event log with partitioned topics (S02), a Pydantic validation gate and internal service layer (S03), three-tier idempotency and circuit breakers (S04), and end-to-end integration validation (S05). All work is additive — no existing test was broken. The full suite grew from ~200 to 231 tests with zero regressions.

## Success Criteria Results

All per-slice verification commands passed. Final full-suite run: 231 passed in 67.49s.

## Definition of Done Results

All 5 slices complete with passing tests. 231 tests green, zero regressions. All 15 active requirements validated. Integration test exercising all M006 components end-to-end. No external processes required (fakeredis throughout).

## Requirement Outcomes

R001–R002: StreamWorker XREADGROUP/ACK/PEL validated. R003–R005: EventLog Protocol + topic helpers validated. R006–R007: ValidationGate + InternalServiceLayer validated. R008–R014: Idempotency + CircuitBreaker validated. R015: Full regression — 231 passed. R016/R017/R018: Remain deferred.

## Deviations

set_vector_store/set_embedder in gateway/app.py needed a fix to propagate to the _service_layer singleton — pre-existing bug exposed by test_s04.py, fixed in S05.

## Follow-ups

R016 (multi-instance horizontal scaling), R017 (real Kafka + docker-compose), R018 (Redlock 3-node quorum) remain deferred for a future milestone when real infrastructure is available.
