# S02 Research: Event Log Abstraction + Partitioned Topics

**Gathered:** 2026-04-01
**Complexity:** Light — well-understood Protocol pattern already in codebase; no new technology

---

## Summary

S02 delivers three requirements on top of the working StreamWorker from S01:

- **R003** — `EventLog` Protocol + `InProcessEventLog` (append-only list); aiokafka adapter stub
- **R004** — Session-partitioned routing: same `session_id` → same Redis Stream
- **R005** — Capability-based topic routing: `task.required_capability` → stream name (e.g. `tasks.search`, `tasks.write`)

All three follow existing codebase patterns exactly. No new libraries required. The test file target is `tests/test_m006_eventlog.py`.

---

## Recommendation

**One task.** Create `src/mcp_agent_factory/streams/eventlog.py` with the `EventLog` Protocol + `InProcessEventLog`, add a `TopicRouter` helper that maps an `AgentTask` to a stream name, and write `tests/test_m006_eventlog.py` covering all three requirements.

---

## Implementation Landscape

### Pattern to follow: `VectorStore` / `InMemoryVectorStore`

`src/mcp_agent_factory/knowledge/vector_store.py` is the canonical Protocol + in-process impl pattern:

```python
class VectorStore(Protocol):
    def upsert(...): ...
    def search(...): ...

class InMemoryVectorStore:
    ...
```

Apply the same structure for `EventLog`:

```python
# src/mcp_agent_factory/streams/eventlog.py

from typing import Protocol, Any

class EventLog(Protocol):
    def append(self, topic: str, event_type: str, payload: dict[str, Any]) -> None: ...
    def events(self, topic: str) -> list[dict[str, Any]]: ...

class InProcessEventLog:
    """Append-only in-memory list per topic. Test double for real aiokafka adapter."""
    def __init__(self) -> None:
        self._log: dict[str, list[dict]] = {}

    def append(self, topic: str, event_type: str, payload: dict[str, Any]) -> None:
        self._log.setdefault(topic, []).append({"event_type": event_type, **payload})

    def events(self, topic: str) -> list[dict[str, Any]]:
        return list(self._log.get(topic, []))
```

### TopicRouter (R004 + R005)

Two routing strategies for stream/topic name derivation:

1. **Session partition (R004):** `f"tasks.session.{session_id}"` — tasks with same session_id → same stream
2. **Capability topic (R005):** `f"tasks.{task.required_capability}"` — e.g. `tasks.search`, `tasks.write`

A simple `TopicRouter` function or class in the same file suffices:

```python
def capability_topic(task: AgentTask) -> str:
    return f"tasks.{task.required_capability}"

def session_topic(task: AgentTask, session_id: str) -> str:
    return f"tasks.session.{session_id}"
```

`AgentTask.required_capability` defaults to `"general"` — this maps to `tasks.general` naturally.

### Test structure for `tests/test_m006_eventlog.py`

The roadmap success criteria:
> two tasks with different session_ids go to different streams; two tasks with same capability go to same stream

```python
def test_session_partitioning():
    # task_a session "s1", task_b session "s2" → different topics
    assert session_topic(task_a, "s1") != session_topic(task_b, "s2")
    # task_c session "s1", task_d session "s1" → same topic
    assert session_topic(task_c, "s1") == session_topic(task_d, "s1")

def test_capability_routing():
    # task_a capability "search", task_b capability "search" → same topic
    assert capability_topic(task_a) == capability_topic(task_b) == "tasks.search"
    # task_c capability "write" → different topic
    assert capability_topic(task_c) == "tasks.write"

def test_eventlog_append_and_read():
    log = InProcessEventLog()
    log.append("tasks.search", "task_start", {"task_id": "abc"})
    log.append("tasks.search", "task_complete", {"task_id": "abc", "result": "ok"})
    log.append("tasks.write", "task_start", {"task_id": "xyz"})
    events = log.events("tasks.search")
    assert len(events) == 2
    assert events[0]["event_type"] == "task_start"
    # tasks.write is independent
    assert len(log.events("tasks.write")) == 1
```

### aiokafka adapter stub (R003)

A stub module `src/mcp_agent_factory/streams/kafka_adapter.py` implementing the `EventLog` protocol using aiokafka is in-scope as a stub. It should contain the class definition with `NotImplementedError` or a conditional import guard — it must NOT be imported in tests (no aiokafka installed). The stub documents the interface contract for when R017 is implemented.

### Files to create

| File | Purpose |
|------|---------|
| `src/mcp_agent_factory/streams/eventlog.py` | `EventLog` Protocol, `InProcessEventLog`, `capability_topic()`, `session_topic()` |
| `src/mcp_agent_factory/streams/kafka_adapter.py` | aiokafka stub implementing `EventLog` (optional/guarded import) |
| `tests/test_m006_eventlog.py` | Tests for R003, R004, R005 |

`src/mcp_agent_factory/streams/__init__.py` exists already (from S01); update exports if needed.

### Constraints

- Tab indentation throughout (project convention)
- Pydantic v2 for any models (none expected in this slice)
- No aiokafka import in test code — tests use only `InProcessEventLog`
- `AgentTask` is at `src/mcp_agent_factory/agents/models.py` — import from there

### No external dependency discovery needed

The Protocol + in-process impl pattern is pure stdlib (`typing.Protocol`, `dict`, `list`). fakeredis is not needed for the EventLog tests (it's an in-process list). StreamWorker fixture pattern from `tests/test_m006_streams.py` can be referenced for consistency but this slice's tests are simpler.
