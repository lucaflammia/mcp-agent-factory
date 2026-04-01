# M006: 

## Vision
Replace in-process communication with Redis Streams consumer groups, add a Kafka-protocol event log, insert a Pydantic validation gate into the gateway, and make the agent pipeline fault-tolerant with three-tier idempotency and circuit breakers — all testable with fakeredis and no external processes.

## Slice Overview
| ID | Slice | Risk | Depends | Done | After this |
|----|-------|------|---------|------|------------|
| S01 | Redis Streams Worker | high | — | ✅ | pytest tests/test_m006_streams.py -v passes — worker claims task, ACKs it, PEL recovery scenario recovers un-ACKed message |
| S02 | Event Log Abstraction + Partitioned Topics | medium | S01 | ✅ | pytest tests/test_m006_eventlog.py -v passes — two tasks with different session_ids go to different streams; two tasks with same capability go to same stream |
| S03 | Validation Gate + Internal Service Layer | medium | S01 | ✅ | pytest tests/test_m006_gateway.py -v passes — malformed payload blocked; valid payload dispatched; existing test_gateway.py still passes |
| S04 | Idempotency + Circuit Breakers | high | S01, S02, S03 | ✅ | pytest tests/test_m006_reliability.py -v passes — idempotency cache hit confirmed, circuit opens after N failures and returns fallback |
| S05 | Integration & Regression | low | S01, S02, S03, S04 | ✅ | pytest tests/ -v passes — all M001–M006 tests green, zero regressions |
