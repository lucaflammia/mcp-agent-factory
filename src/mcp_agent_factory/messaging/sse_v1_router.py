"""
SSE v1 router — /sse/v1 endpoints for production client connectivity.

Endpoints
---------
GET  /sse/v1/events?topic={topic}
    Streams AgentMessage events as Server-Sent Events.
    Sends a synthetic ``connected`` event immediately on subscription
    so clients can confirm the channel is live before waiting for data.

POST /sse/v1/messages
    Publishes a message to the bus.  Useful for injecting test events
    or for gateway-internal tooling; not exposed to the public internet
    without auth middleware.

Both endpoints share the bus injected via ``create_sse_v1_router(bus)``.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from mcp_agent_factory.messaging.bus import AgentMessage, MessageBus

logger = logging.getLogger("mcp_gateway.sse_v1")

DEFAULT_TOPIC = "agent.events"
TIMEOUT_S = 30.0


class PublishBody(BaseModel):
	topic: str = DEFAULT_TOPIC
	sender: str = "gateway"
	recipient: str = "*"
	content: dict = {}


def create_sse_v1_router(bus: MessageBus) -> APIRouter:
	"""
	Factory returning an APIRouter wired to *bus*.

	Mount with::

		app.include_router(create_sse_v1_router(bus), prefix="/sse/v1")
	"""
	router = APIRouter()

	@router.get("/events")
	async def sse_events(topic: str = DEFAULT_TOPIC):
		"""
		Stream AgentMessage events for *topic* as SSE.

		The first event sent is always ``connected`` so clients can confirm
		the channel is live.  Subsequent events carry ``message`` type with
		a JSON-serialised AgentMessage body.  A ``keepalive`` comment is
		emitted every 30 s when the queue is idle.
		"""
		queue = bus.subscribe(topic)
		logger.info("sse.connected topic=%s", topic)

		async def event_generator():
			# Immediate handshake event
			yield {"event": "connected", "data": json.dumps({"topic": topic})}
			try:
				while True:
					try:
						message: AgentMessage = await asyncio.wait_for(
							queue.get(), timeout=TIMEOUT_S
						)
						yield {
							"event": "message",
							"data": json.dumps(message.model_dump()),
						}
					except asyncio.TimeoutError:
						yield {"event": "keepalive", "data": ""}
			except asyncio.CancelledError:
				pass
			finally:
				bus.unsubscribe(topic, queue)
				logger.info("sse.disconnected topic=%s", topic)

		return EventSourceResponse(event_generator())

	@router.post("/messages", status_code=202)
	async def publish_message(body: PublishBody) -> dict:
		"""
		Publish a message to the bus under *body.topic*.

		Returns ``{"published": true}`` on success.
		"""
		msg = AgentMessage(
			topic=body.topic,
			sender=body.sender,
			recipient=body.recipient,
			content=body.content,
		)
		bus.publish(body.topic, msg)
		logger.debug("sse_v1.publish topic=%s sender=%s", body.topic, body.sender)
		return {"published": True}

	return router
