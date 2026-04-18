# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R001 — Redis Streams consumer-group task distribution
- Class: core-capability
- Status: active
- Description: Tasks published to Redis Streams are claimed by exactly one StreamWorker via XREADGROUP; each task is processed by a single consumer instance
- Why it matters: Enables horizontal scaling and prevents duplicate task execution across multiple worker processes
- Source: user
- Primary owning slice: M006/S01
- Supporting slices: M006/S05
- Validation: mapped
- Notes: Uses fakeredis for tests; real redis.asyncio for production

### R002 — PEL-based crash recovery for in-flight tasks
- Class: continuity
- Status: active
- Description: When a worker crashes before ACKing a task, the message remains in the Pending Entries List (PEL) and can be reclaimed by another consumer via XCLAIM/XAUTOCLAIM
- Why it matters: Guarantees at-least-once delivery even under worker failure — no tasks silently dropped
- Source: user
- Primary owning slice: M006/S01
- Supporting slices: M006/S05
- Validation: mapped
- Notes: Test simulates crash by consuming without ACKing, then asserting xpending_range returns the message

### R003 — Kafka-protocol event log for durable execution history
- Class: continuity
- Status: active
- Description: Every task execution (start, complete, fail) is appended to an event log behind a Protocol interface; the in-process implementation is an append-only list; a real aiokafka adapter can be swapped in
- Why it matters: Enables audit trail, replay, and offline analytics without tight coupling to the real broker
- Source: user
- Primary owning slice: M006/S02
- Supporting slices: M006/S05
- Validation: mapped
- Notes: aiokafka not yet installed; EventLog protocol + InProcessEventLog for tests; R017 covers real broker

### R004 — Session-partitioned message ordering
- Class: quality-attribute
- Status: active
- Description: Messages with the same session_id are routed to the same Redis Stream partition key, preserving temporal ordering of multi-turn conversation tasks
- Why it matters: LLM agents that process multi-turn sessions must see turns in order; interleaving breaks context
- Source: user
- Primary owning slice: M006/S02
- Supporting slices: none
- Validation: mapped
- Notes: Implemented via stream-per-session naming convention or explicit partition field

### R005 — Functional topic segregation (tasks.search, tasks.write)
- Class: core-capability
- Status: active
- Description: Tasks are routed to separate Redis Streams by capability type (e.g. tasks.search, tasks.write), allowing independent consumer group scaling per stream
- Why it matters: High-latency write tasks should not block low-latency search tasks; independent scaling is the key production affordance
- Source: user
- Primary owning slice: M006/S02
- Supporting slices: none
- Validation: mapped
- Notes: Stream name derived from task.required_capability field already present on AgentTask

### R006 — Strangler Fig internal service layer in gateway
- Class: core-capability
- Status: active
- Description: The gateway's _mcp_dispatch is refactored into a thin router that delegates tool calls to a discrete InternalServiceLayer; new endpoints can be added to the service layer without touching the routing logic
- Why it matters: Isolates non-deterministic agent logic from the MCP protocol handler, enabling gradual traffic migration
- Source: user
- Primary owning slice: M006/S03
- Supporting slices: M006/S05
- Validation: mapped
- Notes: No actual legacy monolith exists; "Strangler Fig" is embodied as clean separation between protocol routing and business logic

### R007 — Pydantic validation gate blocking malformed agent output
- Class: failure-visibility
- Status: active
- Description: Every agent response passes through a ValidationGate before reaching the dispatch result; responses that fail schema validation return a structured error instead of corrupting downstream state
- Why it matters: LLMs hallucinate output shapes; the gate is the last line of defense before bad data reaches the session store or SSE clients
- Source: user
- Primary owning slice: M006/S03
- Supporting slices: M006/S05
- Validation: mapped
- Notes: Gate rejects payloads with wrong types, missing required fields, or extra fields if strict mode enabled

### R008 — Redis pre-check idempotency (task_id SET NX)
- Class: reliability
- Status: active
- Description: Before executing a task, the worker checks SET task_id NX EX ttl; if the key already exists, the task is skipped as already-processed
- Why it matters: Prevents double-execution when a task is redelivered after a timeout but was already completed by the original worker
- Source: user
- Primary owning slice: M006/S04
- Supporting slices: none
- Validation: mapped
- Notes: First of three idempotency tiers

### R009 — Distributed locking on consumer rebalance (single-node Redlock pattern)
- Class: reliability
- Status: active
- Description: Before processing a claimed task, the worker acquires a short-TTL lock using SET NX EX (single-node Redlock approximation) behind a DistributedLock protocol
- Why it matters: Prevents duplicate execution during consumer group rebalancing when two workers briefly both see the same PEL entry
- Source: user
- Primary owning slice: M006/S04
- Supporting slices: none
- Validation: mapped
- Notes: True Redlock (3-node quorum) is R018 (deferred); single-node is functionally safe in single-process environments

### R010 — Transactional Outbox Pattern for atomic state+dispatch
- Class: reliability
- Status: active
- Description: State updates and outbound message dispatch are written atomically to an in-memory outbox; the outbox relay publishes them only after the state write succeeds
- Why it matters: Prevents the failure window between state write and message publish — either both happen or neither does
- Source: user
- Primary owning slice: M006/S04
- Supporting slices: none
- Validation: mapped
- Notes: In-process implementation; real DB-backed outbox (Postgres, SQLite) is a natural extension

### R011 — Circuit breaker on LLM API calls
- Class: reliability
- Status: active
- Description: A CircuitBreaker wraps every simulated LLM call; after N consecutive failures it opens and returns a fallback response immediately without calling the LLM
- Why it matters: Prevents cascading failures and runaway retry storms when the LLM API is degraded
- Source: user
- Primary owning slice: M006/S04
- Supporting slices: M006/S05
- Validation: mapped
- Notes: States: CLOSED → OPEN → HALF_OPEN; half-open allows one probe call

### R012 — Circuit breaker on vector store calls
- Class: reliability
- Status: active
- Description: Same CircuitBreaker wraps vector store search calls; opens independently of the LLM breaker
- Why it matters: Vector DB degradation should not take down LLM-only paths and vice versa
- Source: user
- Primary owning slice: M006/S04
- Supporting slices: none
- Validation: mapped
- Notes: Shares CircuitBreaker implementation with R011

### R013 — Fallback to "Internal Knowledge" mode on circuit open
- Class: reliability
- Status: active
- Description: When the LLM circuit is open, the worker returns a canned "Internal Knowledge" response from a local cache/static store rather than failing the task outright
- Why it matters: Degrades gracefully — the user gets a response, not an error, when the LLM is unreachable
- Source: user
- Primary owning slice: M006/S04
- Supporting slices: none
- Validation: mapped
- Notes: "Internal Knowledge" is the existing InMemoryVectorStore + LibrarianAgent path

### R014 — No duplicate LLM calls on retry (result caching)
- Class: reliability
- Status: active
- Description: The result of a completed LLM call is cached in Redis against task_id; retries check the cache before calling the LLM and return the cached result if present
- Why it matters: Prevents double token charges and non-deterministic re-generation when a retry fires after the original call succeeded but the ACK was lost
- Source: user
- Primary owning slice: M006/S04
- Supporting slices: none
- Validation: mapped
- Notes: Distinct from R008 (pre-execution check); this is a post-execution cache hit

### R015 — Existing test suite passes with no regressions
- Class: quality-attribute
- Status: active
- Description: All tests from M001–M005 continue to pass after M006 changes; new code is additive not destructive
- Why it matters: The in-process MessageBus and scheduler are not removed — they remain for existing tests and SSE flows
- Source: inferred
- Primary owning slice: M006/S05
- Supporting slices: none
- Validation: mapped
- Notes: StreamWorker and MessageBus coexist; existing imports unchanged

## Deferred

### R016 — Multi-instance horizontal scaling (stateless workers)
- Class: operability
- Status: active
- Description: Multiple StreamWorker processes running in parallel, each in a separate OS process, with correct consumer group semantics across process boundaries
- Why it matters: The real scaling story; single-process testing proves the contract but not the multi-process behaviour
- Source: inferred
- Primary owning slice: M007/S04
- Supporting slices: M007/S05
- Validation: mapped
- Notes: StreamWorker already stateless; test harness uses multiprocessing against real Redis

### R017 — Real Kafka broker + docker-compose
- Class: operability
- Status: active
- Description: A docker-compose.yml that starts a real Kafka broker and Redis instance for integration testing
- Why it matters: Required before the event log abstraction can be exercised end-to-end with a real broker
- Source: inferred
- Primary owning slice: M007/S01
- Supporting slices: M007/S02, M007/S05
- Validation: mapped
- Notes: aiokafka added to optional-dependencies; KafkaEventLog already implements EventLog protocol

### R018 — Redlock across 3+ Redis nodes
- Class: reliability
- Status: active
- Description: True Redlock quorum locking using at least 3 independent Redis nodes
- Why it matters: Single-node SET NX can fail split-brain; quorum Redlock is the production-safe version
- Source: user
- Primary owning slice: M007/S03
- Supporting slices: M007/S04, M007/S05
- Validation: mapped
- Notes: Supersedes D010 (single-node); 3 standalone Redis containers in docker-compose

## Out of Scope

### R019 — Kafka consumer group rebalancing across real broker partitions
- Class: constraint
- Status: out-of-scope
- Description: Real Kafka partition assignment, rebalance protocol, and consumer group coordinator behaviour
- Why it matters: Clarifies that partition semantics in M006 are modelled via Redis Stream naming convention, not real Kafka partitions
- Source: inferred
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: The EventLog protocol abstracts this; real Kafka partition behaviour is deferred with R017

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | active | M006/S01 | M006/S05 | mapped |
| R002 | continuity | active | M006/S01 | M006/S05 | mapped |
| R003 | core-capability | active | M006/S02 | M006/S05 | mapped |
| R004 | quality-attribute | active | M006/S02 | none | mapped |
| R005 | core-capability | active | M006/S02 | none | mapped |
| R006 | core-capability | active | M006/S03 | M006/S05 | mapped |
| R007 | failure-visibility | active | M006/S03 | M006/S05 | mapped |
| R008 | reliability | active | M006/S04 | none | mapped |
| R009 | reliability | active | M006/S04 | none | mapped |
| R010 | reliability | active | M006/S04 | none | mapped |
| R011 | reliability | active | M006/S04 | M006/S05 | mapped |
| R012 | reliability | active | M006/S04 | none | mapped |
| R013 | reliability | active | M006/S04 | none | mapped |
| R014 | reliability | active | M006/S04 | none | mapped |
| R015 | quality-attribute | active | M006/S05 | none | mapped |
| R016 | operability | active | M007/S04 | M007/S05 | mapped |
| R017 | operability | active | M007/S01 | M007/S02, M007/S05 | mapped |
| R018 | reliability | active | M007/S03 | M007/S04, M007/S05 | mapped |
| R019 | constraint | out-of-scope | none | none | n/a |

## Coverage Summary

- Active requirements: 18
- Mapped to slices: 18
- Validated: 15 (R001–R015)
- Unmapped active requirements: 0
