"""
Asyncio in-process message bus for agent-to-agent routing.

Agents publish messages by topic; subscribers receive them via asyncio.Queue.
Multiple subscribers per topic are supported (fan-out). Topics are independent.

Observability: every publish logged at DEBUG with topic, sender, content preview.

Usage::

    bus = MessageBus()
    queue = bus.subscribe("pipeline.events")
    bus.publish("pipeline.events", AgentMessage(topic="pipeline.events", sender="analyst", content={}))
    msg = await queue.get()
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentMessage(BaseModel):
    """A message routed between agents via the MessageBus."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    sender: str
    content: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class MessageBus:
    """
    In-process asyncio pub/sub message bus.

    Thread-safety: designed for single-threaded asyncio use. Do not call
    from multiple threads without external locking.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, topic: str) -> asyncio.Queue:
        """Register a new subscriber for *topic* and return its queue."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers[topic].append(q)
        return q

    def unsubscribe(self, topic: str, queue: asyncio.Queue) -> None:
        """Remove *queue* from the subscriber list for *topic*."""
        if topic in self._subscribers:
            try:
                self._subscribers[topic].remove(queue)
            except ValueError:
                pass

    def publish(self, topic: str, message: AgentMessage) -> None:
        """
        Deliver *message* to all subscribers of *topic*.

        Silently no-ops if there are no subscribers (not an error).
        """
        content_preview = str(message.content)[:80]
        logger.debug(json.dumps({
            "event": "bus_publish",
            "topic": topic,
            "sender": message.sender,
            "message_id": message.id,
            "content_preview": content_preview,
        }))
        for q in self._subscribers.get(topic, []):
            q.put_nowait(message)

    def subscriber_count(self, topic: str) -> int:
        """Return the number of active subscribers for *topic*."""
        return len(self._subscribers.get(topic, []))
