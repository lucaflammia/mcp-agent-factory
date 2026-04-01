# S04: Idempotency + Circuit Breakers

**Goal:** Implement three-tier idempotency (Redis SET NX pre-check, DistributedLock, OutboxRelay) and CircuitBreaker state machine with Internal Knowledge fallback — all wired into the StreamWorker dispatch path.
**Demo:** After this: pytest tests/test_m006_reliability.py -v passes — idempotency cache hit confirmed, circuit opens after N failures and returns fallback

## Tasks
