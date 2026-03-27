"""
Tests for MessageBus pub/sub and SSE transport.
"""
from __future__ import annotations

import asyncio
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mcp_agent_factory.messaging.bus import AgentMessage, MessageBus
from mcp_agent_factory.messaging.sse_router import create_sse_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def sample_message():
    return AgentMessage(
        topic="pipeline.events",
        sender="analyst-agent",
        content={"result": "analysis_done", "metrics_count": 3},
    )


# ---------------------------------------------------------------------------
# MessageBus unit tests
# ---------------------------------------------------------------------------

class TestMessageBus:
    def test_subscribe_returns_queue(self, bus):
        q = bus.subscribe("topic.a")
        assert isinstance(q, asyncio.Queue)

    async def test_publish_delivers_to_subscriber(self, bus, sample_message):
        q = bus.subscribe("pipeline.events")
        bus.publish("pipeline.events", sample_message)
        received = q.get_nowait()
        assert received.id == sample_message.id
        assert received.sender == "analyst-agent"

    async def test_publish_multi_subscriber_same_topic(self, bus, sample_message):
        q1 = bus.subscribe("topic.shared")
        q2 = bus.subscribe("topic.shared")
        msg = AgentMessage(topic="topic.shared", sender="s", content={})
        bus.publish("topic.shared", msg)
        assert q1.get_nowait().id == msg.id
        assert q2.get_nowait().id == msg.id

    async def test_publish_topic_isolation(self, bus):
        q_a = bus.subscribe("topic.A")
        q_b = bus.subscribe("topic.B")
        msg = AgentMessage(topic="topic.A", sender="s", content={})
        bus.publish("topic.A", msg)
        # q_a should have the message; q_b should be empty
        assert not q_a.empty()
        assert q_b.empty()

    async def test_unsubscribe_stops_delivery(self, bus):
        q = bus.subscribe("topic.unsub")
        bus.unsubscribe("topic.unsub", q)
        bus.publish("topic.unsub", AgentMessage(topic="topic.unsub", sender="s", content={}))
        assert q.empty()

    def test_subscriber_count(self, bus):
        assert bus.subscriber_count("empty.topic") == 0
        bus.subscribe("count.topic")
        bus.subscribe("count.topic")
        assert bus.subscriber_count("count.topic") == 2

    def test_publish_no_subscribers_no_error(self, bus):
        # Should not raise even with zero subscribers
        bus.publish("nobody.listening", AgentMessage(topic="nobody.listening", sender="s", content={}))

    async def test_publish_logs_debug(self, bus, caplog):
        q = bus.subscribe("log.topic")
        msg = AgentMessage(topic="log.topic", sender="test-agent", content={"x": 1})
        with caplog.at_level(logging.DEBUG, logger="mcp_agent_factory.messaging.bus"):
            bus.publish("log.topic", msg)
        log_messages = [r.message for r in caplog.records]
        parsed = [json.loads(m) for m in log_messages if m.startswith("{")]
        pub_logs = [p for p in parsed if p.get("event") == "bus_publish"]
        assert len(pub_logs) == 1
        assert pub_logs[0]["topic"] == "log.topic"
        assert pub_logs[0]["sender"] == "test-agent"

    async def test_message_content_preserved(self, bus):
        q = bus.subscribe("content.topic")
        payload = {"key": "value", "number": 42}
        msg = AgentMessage(topic="content.topic", sender="s", content=payload)
        bus.publish("content.topic", msg)
        received = q.get_nowait()
        assert received.content == payload


# ---------------------------------------------------------------------------
# SSE router tests
# ---------------------------------------------------------------------------

class TestSSERouter:
    def _make_app(self, bus: MessageBus) -> FastAPI:
        app = FastAPI()
        router = create_sse_router(bus)
        app.include_router(router)
        return app

    def test_sse_router_registers_events_endpoint(self, bus):
        """Verify the /events route is registered on the app."""
        app = self._make_app(bus)
        routes = [r.path for r in app.routes]
        assert "/events" in routes

    def test_sse_subscriber_count_before_connection(self, bus):
        """Before any connection, subscriber count is 0."""
        assert bus.subscriber_count("agent.events") == 0

    async def test_message_bus_queue_delivers_before_sse(self, bus):
        """
        Prove the data pathway that SSE relies on works end-to-end:
        publish → queue → subscriber receives the correct AgentMessage.
        SSE just wraps this queue in an HTTP stream.
        """
        q = bus.subscribe("agent.events")
        msg = AgentMessage(topic="agent.events", sender="analyst", content={"step": "done"})
        bus.publish("agent.events", msg)
        received = q.get_nowait()
        assert received.id == msg.id
        assert received.sender == "analyst"
        assert received.content == {"step": "done"}
        # Verify it serializes cleanly to JSON (what SSE would send as data:)
        serialized = json.loads(received.model_dump_json())
        assert serialized["topic"] == "agent.events"
