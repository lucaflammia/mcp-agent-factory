---
estimated_steps: 1
estimated_files: 4
skills_used: []
---

# T01: Implement EventLog abstraction, TopicRouter, aiokafka stub, and tests

Create src/mcp_agent_factory/streams/eventlog.py with EventLog Protocol, InProcessEventLog, capability_topic(), and session_topic(). Create src/mcp_agent_factory/streams/kafka_adapter.py as a guarded-import aiokafka stub. Update streams __init__.py to export the new symbols. Write tests/test_m006_eventlog.py covering R003 (append/read), R004 (session partitioning), and R005 (capability routing).

## Inputs

- ``src/mcp_agent_factory/streams/__init__.py` — existing streams package init`
- ``src/mcp_agent_factory/streams/worker.py` — reference for tab-indentation and coding style`
- ``src/mcp_agent_factory/agents/models.py` — AgentTask model to import`

## Expected Output

- ``src/mcp_agent_factory/streams/eventlog.py` — EventLog Protocol, InProcessEventLog, capability_topic, session_topic`
- ``src/mcp_agent_factory/streams/kafka_adapter.py` — KafkaEventLog stub with guarded aiokafka import`
- ``src/mcp_agent_factory/streams/__init__.py` — updated exports`
- ``tests/test_m006_eventlog.py` — 3 passing tests covering R003, R004, R005`

## Verification

pytest tests/test_m006_eventlog.py -v
