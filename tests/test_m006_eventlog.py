"""
tests/test_m006_eventlog.py — covers R003, R004, R005.

R003: EventLog append/read round-trip
R004: Tasks with different session_ids go to different streams
R005: Tasks with the same capability go to the same stream
"""
import asyncio

import pytest

from mcp_agent_factory.streams import (
	InProcessEventLog,
	capability_topic,
	session_topic,
)
from mcp_agent_factory.agents.models import AgentTask


# ---------------------------------------------------------------------------
# R003: append then read returns the same event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_r003_append_read_roundtrip():
	"""Appending an event and reading it back returns the original payload."""
	log = InProcessEventLog()
	task = AgentTask(name="echo", payload={"x": 1}, required_capability="general")
	topic = capability_topic(task.required_capability)

	msg_id = await log.append(topic, task.model_dump())

	entries = await log.read(topic)
	assert len(entries) == 1
	entry_id, event = entries[0]
	assert entry_id == msg_id
	assert event["id"] == task.id
	assert event["name"] == "echo"
	assert event["payload"] == {"x": 1}


# ---------------------------------------------------------------------------
# R004: tasks with different session_ids go to different streams
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_r004_different_sessions_different_streams():
	"""Two tasks with distinct session_ids are routed to independent topics."""
	log = InProcessEventLog()
	task_a = AgentTask(name="task-a", required_capability="general")
	task_b = AgentTask(name="task-b", required_capability="general")

	topic_a = session_topic("session-alpha")
	topic_b = session_topic("session-beta")

	await log.append(topic_a, task_a.model_dump())
	await log.append(topic_b, task_b.model_dump())

	entries_a = await log.read(topic_a)
	entries_b = await log.read(topic_b)

	# Each stream contains exactly its own task
	assert len(entries_a) == 1
	assert len(entries_b) == 1
	assert entries_a[0][1]["name"] == "task-a"
	assert entries_b[0][1]["name"] == "task-b"

	# The two topics are distinct
	assert topic_a != topic_b
	assert topic_a == "session.session-alpha"
	assert topic_b == "session.session-beta"


# ---------------------------------------------------------------------------
# R005: tasks with the same capability go to the same stream
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_r005_same_capability_same_stream():
	"""Two tasks that share a capability are appended to the same topic."""
	log = InProcessEventLog()
	task_1 = AgentTask(name="task-1", required_capability="summarizer")
	task_2 = AgentTask(name="task-2", required_capability="summarizer")

	topic = capability_topic("summarizer")

	await log.append(topic, task_1.model_dump())
	await log.append(topic, task_2.model_dump())

	entries = await log.read(topic)
	assert len(entries) == 2
	names = [e[1]["name"] for e in entries]
	assert "task-1" in names
	assert "task-2" in names
	assert topic == "capability.summarizer"
