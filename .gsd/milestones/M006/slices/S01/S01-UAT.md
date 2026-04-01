# S01: Redis Streams Worker — UAT

**Milestone:** M006
**Written:** 2026-04-01T14:21:43.118Z

## UAT: S01 — Redis Streams Worker

### Preconditions
- Python environment with fakeredis >= 2.34.1 installed
- `src/mcp_agent_factory/streams/worker.py` present
- Run from repo root: `cd /path/to/mcp-agent-factory`

---

### TC-01: Worker claims a task and ACK clears the PEL (R001)

**Steps:**
1. Create a fakeredis client: `client = fakeredis.FakeRedis()`
2. Instantiate `StreamWorker(client, "tasks", "grp", "w1")`
3. Call `worker.ensure_group()`
4. Publish a task: `msg_id = worker.publish(AgentTask(task_id="t1", task_name="n", task_payload={}, required_capability="search"))`
5. Call `worker.claim_one()` → expect `(msg_id_bytes, fields_dict)` not None
6. Call `worker.ack(msg_id_bytes)`
7. Call `client.xpending_range("tasks", "grp", min="-", max="+", count=10)` → expect `[]`

**Expected outcome:** PEL is empty after ACK; no pending messages remain.

---

### TC-02: Un-ACKed message stays in PEL and is recovered (R002)

**Steps:**
1. Create a fakeredis client: `client = fakeredis.FakeRedis()`
2. Instantiate two workers: `w1 = StreamWorker(client, "tasks", "grp", "w1")`, `w2 = StreamWorker(client, "tasks", "grp", "w2")`
3. Call `w1.ensure_group()`
4. Publish a task via `w1.publish(...)`
5. Call `w1.claim_one()` — do NOT call `ack`
6. Assert `client.xpending_range("tasks", "grp", min="-", max="+", count=10)` returns 1 entry
7. Call `w2.recover(min_idle_ms=0, new_consumer="w2")` → expect list with 1 `(msg_id, fields)` tuple

**Expected outcome:** Crashed consumer's message is reclaimed by recovery consumer.

---

### TC-03: claim_one on empty stream returns None

**Steps:**
1. Create `StreamWorker(fakeredis.FakeRedis(), "tasks", "grp", "w1")`
2. Call `worker.ensure_group()`
3. Call `worker.claim_one()` without publishing anything

**Expected outcome:** Returns `None`.

---

### TC-04: ensure_group is idempotent (BUSYGROUP guard)

**Steps:**
1. Create worker and call `worker.ensure_group()` twice on same stream+group

**Expected outcome:** No exception raised on second call; group exists once.

---

### Run all UAT cases automatically:
```
pytest tests/test_m006_streams.py -v
```
Expected: `3 passed`

