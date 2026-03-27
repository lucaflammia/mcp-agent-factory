"""
SSE router for streaming AgentMessage events to external clients.

Exposes GET /events?topic={topic} as a Server-Sent Events endpoint.
Each SSE event carries a JSON-serialized AgentMessage as its data field.

The router is created via create_sse_router(bus) so the MessageBus
can be injected — enabling both production use and test substitution.

Usage::

    bus = MessageBus()
    router = create_sse_router(bus)
    app.include_router(router)

    # In a test — publish before the SSE client connects:
    bus.publish("agent.events", AgentMessage(...))
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from mcp_agent_factory.messaging.bus import AgentMessage, MessageBus


def create_sse_router(bus: MessageBus) -> APIRouter:
    """
    Factory returning an APIRouter with the SSE /events endpoint wired
    to the provided *bus*.
    """
    router = APIRouter()

    @router.get("/events")
    async def sse_events(topic: str = "agent.events"):
        """
        Stream AgentMessage events for *topic* as Server-Sent Events.

        Subscribes to the bus on connection; unsubscribes on disconnect.
        """
        queue = bus.subscribe(topic)

        async def event_generator():
            try:
                while True:
                    try:
                        message: AgentMessage = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield {
                            "event": "message",
                            "data": json.dumps(message.model_dump()),
                        }
                    except asyncio.TimeoutError:
                        # Send keepalive comment
                        yield {"event": "keepalive", "data": ""}
            except asyncio.CancelledError:
                pass
            finally:
                bus.unsubscribe(topic, queue)

        return EventSourceResponse(event_generator())

    return router
