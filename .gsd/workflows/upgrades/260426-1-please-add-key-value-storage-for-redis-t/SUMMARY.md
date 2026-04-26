# Summary — Add Redis Key-Value Storage

**Date:** 2026-04-26  
**Branch:** gsd/dep-upgrade/please-add-key-value-storage-for-redis-t  
**Commit:** aa76915

## What was done

Added `src/mcp_agent_factory/kv/` — a topic-namespaced Redis KV store.

### New files

| File | Purpose |
|---|---|
| `src/mcp_agent_factory/kv/__init__.py` | Package export |
| `src/mcp_agent_factory/kv/store.py` | `RedisKVStore` implementation |
| `tests/test_kv_store.py` | 7 unit tests (fakeredis) |

### Design

`RedisKVStore(client, topics=[...])` namespaces keys as `kv:<topic>:<key>`.
Registered topics are validated at call time; unknown topics raise `ValueError`.
Values are JSON-serialised, supporting dicts, lists, primitives.

## Dependencies changed

None — `redis>=5` and `fakeredis>=2.0` were already declared.

## Test results

```
7 passed in 0.84s
```

## Deferred

None.
