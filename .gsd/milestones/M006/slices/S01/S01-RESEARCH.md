# S01 Research: Redis Streams Worker

**Requirements owned:** R001 (XREADGROUP consumer group), R002 (PEL crash recovery)

---

## Summary

S01 is a targeted implementation slice. All fakeredis APIs needed are verified working; the existing session/manager.py pattern provides the exact client setup to replicate. No new dependencies required. The planner can go straight to implementation.

---

## Recommendation

Create `src/mcp_agent_factory/streams/worker.py` with a `StreamWorker` class. Write `tests/test_m006_streams.py` covering: publish → claim → ack, and crash → PEL surfacing → xclaim recovery.

---

## Implementation Landscape

### Verified fakeredis API (fakeredis 2.34.1)

All calls use **keyword-form streams dict**, not positional `streams` arg (that's what caused the `TypeError: multiple values` error seen during research):

```python
r.xgroup_create(stream, group, id=0, mkstream=True)
r.xadd(stream, fields_dict)
r.xreadgroup(group, consumer, {stream: '>'}, count=N)  # streams as kwarg dict
r.xack(stream, group, message_id)
r.xpending_range(stream, group, min='-', max='+', count=N)
r.xclaim(stream, group, consumer, min_idle_time_ms, [message_id])
```

All confirmed working in isolation.

### Files to create

| Path | Purpose |
|------|---------|
| `src/mcp_agent_factory/streams/__init__.py` | package marker |
| `src/mcp_agent_factory/streams/worker.py` | StreamWorker class |
| `tests/test_m006_streams.py` | R001 + R002 test coverage |

### No files to modify

MessageBus and TaskScheduler are untouched per D011.

### StreamWorker design

```python
class StreamWorker:
    def __init__(self, client, stream: str, group: str, consumer: str):
        ...
    def ensure_group(self) -> None:
        # xgroup_create with mkstream=True; ignore BUSYGROUP error
    def publish(self, task: AgentTask) -> str:
        # xadd — serialize task fields to str; return message_id
    def claim_one(self) -> tuple[bytes, dict] | None:
        # xreadgroup(group, consumer, {stream: '>'}, count=1)
        # return (msg_id, fields) or None
    def ack(self, msg_id: bytes) -> None:
        # xack
    def recover(self, min_idle_ms: int, new_consumer: str) -> list:
        # xpending_range + xclaim
```

Use **sync** fakeredis.FakeRedis for tests (matches the verified API above). The session manager uses async aioredis — StreamWorker can start sync (simpler tests) and wrap with asyncio.to_thread if async is needed later. Tests don't require async.

### AgentTask serialization to stream fields

Redis stream fields must be `str → str` (or `bytes`). Serialize with:
- `task_id = task.id`
- `task_name = task.name`
- `task_payload = json.dumps(task.payload)`
- `task_capability = task.required_capability`

### BUSYGROUP error handling

`xgroup_create` raises `ResponseError: BUSYGROUP Consumer Group name already exists` if the group already exists. Catch `redis.exceptions.ResponseError` and ignore when message contains "BUSYGROUP".

### Test structure for test_m006_streams.py

```
test_worker_claim_and_ack        # R001: publish → claim_one → ack → xpending empty
test_worker_pel_recovery         # R002: publish → claim without ack → xpending non-empty → recover → xclaim returns message
test_worker_no_messages          # claim_one returns None when stream empty
```

### Tab indentation

All new files must use tab indentation (project-wide convention per K001).
