---
estimated_steps: 18
estimated_files: 1
skills_used: []
---

# T01: MessageBus and SSE router

1. Create src/mcp_agent_factory/messaging/__init__.py
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

## Inputs

- `src/mcp_agent_factory/agents/models.py`

## Expected Output

- `src/mcp_agent_factory/messaging/__init__.py`
- `src/mcp_agent_factory/messaging/bus.py`
- `src/mcp_agent_factory/messaging/sse_router.py`

## Verification

python -c "from mcp_agent_factory.messaging.bus import MessageBus, AgentMessage; from mcp_agent_factory.messaging.sse_router import create_sse_router; print('imports ok')"
