---
slice: S04
milestone: M009
title: Async Prompt Cache & Token Cost Tracking
status: complete
---

# S04 Summary — Async Prompt Cache & Token Cost Tracking

## One-liner
AsyncIdempotencyGuard caches prompts by stable SHA-256 hash; cache hits skip the router entirely; token.usage events are readable from EventLog per sub.

## What was built
- `src/mcp_agent_factory/streams/async_idempotency.py` — `AsyncIdempotencyGuard` with stable SHA-256 prompt hashing, async `get(key)` / `set(key, value)`, write-failure swallowing
- `src/mcp_agent_factory/gateway/service_layer.py` — prompt cache wired into `sampling_demo`: cache hit skips the router entirely

## Verification
`pytest tests/test_m009_s04.py` — 11 passed.

Confirmed:
- Identical prompt yields cache hit (sub-1ms on second call)
- Hash is stable across multiple calls with same input
- Cache write failure logged but does not propagate
- Cache read failure falls through to router
- Router is skipped on cache hit
- token.usage events readable per sub from EventLog

## Requirements advanced
- R037: Async prompt cache with stable hashing (validated)
- R038: token.usage events readable per sub (validated)
