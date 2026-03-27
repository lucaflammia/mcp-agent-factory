# S03: Async Message Bus + SSE Transport

**Goal:** Implement asyncio MessageBus for agent-to-agent message routing by topic, and a FastAPI SSE router that streams bus messages to connected external clients.
**Demo:** After this: pytest tests/test_message_bus.py -v passes; SSE endpoint streams AgentMessage events to a test client.

## Tasks
- [x] **T01: MessageBus asyncio pub/sub and SSE EventSourceResponse router — factory-injectable for tests.** — 1. Create src/mcp_agent_factory/messaging/__init__.py
2. Create src/mcp_agent_factory/messaging/bus.py:
   - AgentMessage(BaseModel): id (uuid4), topic (str), sender (str), content (dict), timestamp (float = time.time())
   - MessageBus:
     - _subscribers: dict[str, list[asyncio.Queue]] — topic -> list of subscriber queues
     - publish(topic: str, message: AgentMessage) -> None: put message on all queues for topic; log at DEBUG
     - subscribe(topic: str) -> asyncio.Queue: create new queue, register it, return it
     - unsubscribe(topic: str, queue: asyncio.Queue) -> None: remove queue from topic list
     - subscriber_count(topic: str) -> int: len(_subscribers[topic])
3. Create src/mcp_agent_factory/messaging/sse_router.py:
   - Create FastAPI APIRouter
   - GET /events?topic={topic} endpoint:
     - Creates a subscriber queue via MessageBus.subscribe(topic)
     - Returns EventSourceResponse (sse_starlette) that yields messages as SSE data
     - Each SSE event: data=json.dumps(message.model_dump())
     - Unsubscribes on generator completion/disconnect
   - Accepts bus: MessageBus as a parameter (injectable for tests)
4. Export create_sse_router(bus: MessageBus) -> APIRouter factory function
  - Estimate: 25min
  - Files: src/mcp_agent_factory/messaging/
  - Verify: python -c "from mcp_agent_factory.messaging.bus import MessageBus, AgentMessage; from mcp_agent_factory.messaging.sse_router import create_sse_router; print('imports ok')"
- [x] **T02: 12 message bus tests \u2014 pub/sub, fan-out, isolation, SSE route registration, queue delivery — all passing.** — 1. Create tests/test_message_bus.py
2. MessageBus unit tests:
   - test_subscribe_returns_queue
   - test_publish_delivers_to_subscriber
   - test_publish_multi_subscriber_same_topic
   - test_publish_topic_isolation (msg on topic A not delivered to topic B subscriber)
   - test_unsubscribe_stops_delivery
   - test_subscriber_count
   - test_publish_no_subscribers_no_error
3. SSE endpoint tests (using FastAPI TestClient with stream=True):
   - test_sse_endpoint_streams_message: publish one message, TestClient streams it, parse SSE data line
   - Note: SSE with TestClient requires careful handling — publish message BEFORE connecting or use background thread
   - Use a pre-published message approach: publish to bus before creating SSE response
4. Keep SSE test simple and reliable — use asyncio.Queue directly if TestClient SSE streaming is flaky
  - Estimate: 25min
  - Files: tests/test_message_bus.py
  - Verify: python -m pytest tests/test_message_bus.py -v
