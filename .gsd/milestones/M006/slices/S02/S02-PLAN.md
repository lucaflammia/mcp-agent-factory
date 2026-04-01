# S02: Event Log Abstraction + Partitioned Topics

**Goal:** Add EventLog Protocol + InProcessEventLog, TopicRouter helpers (session_topic, capability_topic), and aiokafka stub; prove R003/R004/R005 with tests/test_m006_eventlog.py.
**Demo:** After this: pytest tests/test_m006_eventlog.py -v passes — two tasks with different session_ids go to different streams; two tasks with same capability go to same stream

## Tasks
- [x] **T01: Added EventLog Protocol, InProcessEventLog, TopicRouter helpers, KafkaEventLog stub, and 3 passing tests covering R003/R004/R005** — Create src/mcp_agent_factory/streams/eventlog.py with EventLog Protocol, InProcessEventLog, capability_topic(), and session_topic(). Create src/mcp_agent_factory/streams/kafka_adapter.py as a guarded-import aiokafka stub. Update streams __init__.py to export the new symbols. Write tests/test_m006_eventlog.py covering R003 (append/read), R004 (session partitioning), and R005 (capability routing).
  - Estimate: 30m
  - Files: src/mcp_agent_factory/streams/eventlog.py, src/mcp_agent_factory/streams/kafka_adapter.py, src/mcp_agent_factory/streams/__init__.py, tests/test_m006_eventlog.py
  - Verify: pytest tests/test_m006_eventlog.py -v
