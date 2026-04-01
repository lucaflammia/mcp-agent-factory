# S01: Redis Streams Worker

**Goal:** Implement StreamWorker with XREADGROUP-based task claiming, ACK, and PEL-based crash recovery, exercised entirely via fakeredis with no external processes.
**Demo:** After this: pytest tests/test_m006_streams.py -v passes — worker claims task, ACKs it, PEL recovery scenario recovers un-ACKed message

## Tasks
- [x] **T01: Add StreamWorker with XREADGROUP claim/ACK/PEL recovery and passing fakeredis tests** — Create src/mcp_agent_factory/streams/__init__.py and src/mcp_agent_factory/streams/worker.py with the StreamWorker class, then write tests/test_m006_streams.py covering R001 (claim+ack) and R002 (PEL crash recovery).

StreamWorker interface:
- __init__(self, client, stream: str, group: str, consumer: str)
- ensure_group() → xgroup_create with mkstream=True; catch ResponseError containing 'BUSYGROUP' and ignore
- publish(task: AgentTask) → str: xadd with fields {task_id, task_name, task_payload (json.dumps), task_capability}; return message_id as str
- claim_one() → tuple[bytes, dict] | None: xreadgroup(group, consumer, {stream: '>'}, count=1); return (msg_id, fields) or None
- ack(msg_id: bytes) → None: xack
- recover(min_idle_ms: int, new_consumer: str) → list: xpending_range(stream, group, min='-', max='+', count=10) then xclaim each; return list of (msg_id, fields) tuples

Critical: use streams as a keyword dict in xreadgroup — NOT positional. fakeredis 2.34.1 raises TypeError on positional 'streams' arg. Use tab indentation (K001).

Test cases:
1. test_worker_claim_and_ack: publish → claim_one returns (msg_id, fields) → ack → xpending_range returns [] (R001)
2. test_worker_pel_recovery: publish → claim_one without ack → xpending_range non-empty → recover() returns the message (R002)
3. test_worker_no_messages: claim_one on empty stream returns None
  - Estimate: 45m
  - Files: src/mcp_agent_factory/streams/__init__.py, src/mcp_agent_factory/streams/worker.py, tests/test_m006_streams.py
  - Verify: pytest tests/test_m006_streams.py -v
