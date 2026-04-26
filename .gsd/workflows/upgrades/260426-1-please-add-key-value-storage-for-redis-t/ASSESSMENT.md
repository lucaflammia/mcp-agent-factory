# Assessment — Add Redis Key-Value Storage

**Date:** 2026-04-26

## Scope

This is a feature addition, not a version bump. The request: add topic-namespaced
key-value storage backed by the existing `redis>=5` dependency and write tests.

## Current state

| Dependency | Current spec | Installed |
|---|---|---|
| redis | `>=5` | 5.x |
| fakeredis | `>=2.0` (dev) | 2.x |

Both are already present — no new dependencies required.

## Existing Redis usage

- `session/manager.py` — `RedisSessionManager` (flat JSON KV, no namespacing)
- `streams/` — eventlog, idempotency, redlock (stream/lock primitives)

## Plan

Add `src/mcp_agent_factory/kv/` module with `RedisKVStore`:
- Topic-based namespacing (`kv:<topic>:<key>`)
- `set / get / delete / keys` async interface
- Rejects unknown topics at construction time
- Tests via `fakeredis.aioredis` (no live Redis needed)

## Risk

Low — additive only, no existing code modified.
