# M006: Distributed Orchestration & Monolith Refactoring

**Gathered:** 2026-04-01
**Status:** Ready for planning

## Project Description

Evolve the MCP Agent Factory from in-process communication to a distributed, fault-tolerant architecture. Replace the asyncio MessageBus and heap TaskScheduler with Redis Streams consumer groups for task distribution, add a Kafka-protocol event log for durable execution history, insert a Pydantic validation gate into the gateway dispatch path, and add three-tier idempotency plus circuit breakers on all external calls.

## Why This Milestone

The existing MessageBus and TaskScheduler are in-process only — they cannot span multiple worker processes and offer no crash recovery. This milestone makes the task distribution layer genuinely distributed (one task claimed by exactly one worker, PEL-based recovery on crash) and makes the agent pipeline fault-tolerant (idempotency prevents double LLM calls, circuit breakers prevent cascading failures).

## User-Visible Outcome

### When this milestone is complete, the user can:

- Publish a task to a Redis Stream and watch it claimed, processed, and ACKed by a StreamWorker
- Kill a worker mid-task and prove the PEL holds the message for recovery via XCLAIM
- Send a malformed agent payload to the gateway and receive a structured validation error, not a crash
- Trigger N consecutive LLM failures and watch the circuit open and return an "Internal Knowledge" fallback
- Retry a completed task and confirm no second LLM call fires (cache hit)

### Entry point / environment

- Entry point: `PYTHONPATH=src pytest tests/test_m006_*.py -v`
- Environment: local dev with fakeredis; real Redis optional
- Live dependencies involved: fakeredis (streams), in-process EventLog, InMemoryVectorStore

## Completion Class

- Contract complete means: all tests in tests/test_m006_*.py pass; fakeredis exercises full stream/consumer-group contract
- Integration complete means: StreamWorker, ValidationGate, IdempotencyGuard, CircuitBreaker, and EventLog are wired through a single end-to-end test scenario
- Operational complete means: none (real Redis deployment is R017, deferred)

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- A task published to a Redis Stream is claimed and ACKed by a StreamWorker; an un-ACKed task surfaces in the PEL
- A malformed agent payload is blocked by the ValidationGate and returns a structured error
- A retry after simulated LLM timeout does not trigger a second LLM call (idempotency cache hit)
- After N failures, the CircuitBreaker opens and returns the Internal Knowledge fallback
- `pytest tests/` passes in full with no regressions

## Risks and Unknowns

- Redis Streams consumer group semantics in fakeredis — verified: xreadgroup, xack, xpending_range, xclaim all work in fakeredis 2.34.1
- Kafka abstraction boundary — the EventLog protocol must be thin enough that tests run without aiokafka; InProcessEventLog is the test double
- Redlock on single node — SET NX EX is correct and safe for single-process environments; multi-node quorum is R018 (deferred)
- Coexistence with existing MessageBus — StreamWorker and MessageBus must not conflict; they serve different layers (distributed task intake vs in-process fan-out for SSE)

## Existing Codebase / Prior Art

- `src/mcp_agent_factory/messaging/bus.py` — existing in-process MessageBus; NOT removed; coexists with StreamWorker
- `src/mcp_agent_factory/scheduler.py` — existing asyncio heap scheduler; NOT removed; coexists
- `src/mcp_agent_factory/session/manager.py` — RedisSessionManager using fakeredis; StreamWorker reuses same client pattern
- `src/mcp_agent_factory/gateway/app.py` — _mcp_dispatch is the insertion point for the InternalServiceLayer and ValidationGate
- `src/mcp_agent_factory/agents/models.py` — AgentTask has id, name, payload, complexity, required_capability — required_capability drives topic routing (R005)
- `src/mcp_agent_factory/knowledge/vector_store.py` — InMemoryVectorStore; circuit breaker wraps its search() call (R012)

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions.

## Relevant Requirements

- R001, R002 — Redis Streams worker and PEL recovery (S01)
- R003, R004, R005 — Event log + partitioned topics (S02)
- R006, R007 — Strangler Fig service layer + validation gate (S03)
- R008–R014 — Idempotency tiers + circuit breakers (S04)
- R015 — Regression guard (S05)

## Scope

### In Scope

- StreamWorker: XADD publisher, XREADGROUP consumer, XACK, PEL recovery via XCLAIM
- EventLog Protocol + InProcessEventLog (append-only list); aiokafka adapter stub
- InternalServiceLayer extracted from gateway _mcp_dispatch
- ValidationGate: Pydantic model wrapping every tool-call result
- IdempotencyGuard: SET NX pre-check + DistributedLock (SET NX EX) + OutboxRelay
- CircuitBreaker: CLOSED/OPEN/HALF_OPEN state machine, configurable threshold and timeout
- Internal Knowledge fallback using existing LibrarianAgent
- Full regression test run in S05

### Out of Scope / Non-Goals

- Real Kafka broker / docker-compose (R017, deferred)
- Multi-node Redlock (R018, deferred)
- Multi-process worker deployment (R016, deferred)
- Removing or replacing MessageBus or TaskScheduler (they coexist)

## Technical Constraints

- Tab indentation throughout
- All new modules under `src/mcp_agent_factory/` following existing package structure
- Tests use fakeredis; no external processes required to run the test suite
- Pydantic v2 for all models
- New dependencies (aiokafka) added to pyproject.toml as optional; not required for tests

## Integration Points

- fakeredis.FakeRedis — used by StreamWorker tests; same client type as session/manager.py
- gateway/app.py — ValidationGate and InternalServiceLayer inserted into _mcp_dispatch
- knowledge/ — LibrarianAgent + InMemoryVectorStore used as Internal Knowledge fallback

## Open Questions

- None — all material decisions resolved in discussion
