# S02: Event Log Abstraction + Partitioned Topics — UAT

**Milestone:** M006
**Written:** 2026-04-01T14:26:36.771Z

## UAT: S02 — Event Log Abstraction + Partitioned Topics

### Preconditions
- Python environment with project installed (`pip install -e .`)
- No external broker required (InProcessEventLog is in-memory)
- pytest and pytest-asyncio available

---

### TC-01: Append/Read Roundtrip (R003)

**Objective:** Verify that an event appended to a topic can be read back at the correct offset.

**Steps:**
1. Instantiate `InProcessEventLog()`
2. Call `await log.append("topic-a", {"type": "task_start", "task_id": "t1"})`
3. Call `events = await log.read("topic-a", offset=0)`
4. Assert `len(events) == 1` and `events[0]["task_id"] == "t1"`

**Expected:** Single event returned with matching payload. No errors raised.

**Run:** `pytest tests/test_m006_eventlog.py::test_r003_append_read_roundtrip -v`

---

### TC-02: Session Partitioning — Different Sessions → Different Streams (R004)

**Objective:** Verify that two tasks with different `session_id` values are routed to different stream keys.

**Steps:**
1. Call `topic_a = session_topic("session-alice")`
2. Call `topic_b = session_topic("session-bob")`
3. Assert `topic_a != topic_b`
4. Append an event to `topic_a` and a different event to `topic_b`
5. Read from each topic independently
6. Assert each topic contains only its own event

**Expected:** Topics are distinct; reads are isolated.

**Run:** `pytest tests/test_m006_eventlog.py::test_r004_different_sessions_different_streams -v`

---

### TC-03: Capability Routing — Same Capability → Same Stream (R005)

**Objective:** Verify that two tasks with the same capability are routed to the same stream regardless of session.

**Steps:**
1. Call `t1 = capability_topic("search")`
2. Call `t2 = capability_topic("search")`
3. Assert `t1 == t2`
4. Append events from two different sessions to `capability_topic("search")`
5. Read from `capability_topic("search")`
6. Assert both events are present in the same topic

**Expected:** Single topic contains both events; capability routing is deterministic.

**Run:** `pytest tests/test_m006_eventlog.py::test_r005_same_capability_same_stream -v`

---

### TC-04: Full Suite Regression

**Objective:** Confirm no regressions in the broader test suite.

**Steps:**
1. Run `pytest tests/test_m006_eventlog.py -v`
2. Verify all 3 tests pass

**Expected:** `3 passed` with zero failures or errors.

---

### TC-05: KafkaEventLog Importable Without aiokafka

**Objective:** Verify the package is importable and `KafkaEventLog` is accessible even without aiokafka installed.

**Steps:**
1. In a Python REPL: `from mcp_agent_factory.streams import KafkaEventLog`
2. Assert no `ImportError` is raised

**Expected:** Import succeeds; `KafkaEventLog` is a class (stub).

