---
estimated_steps: 14
estimated_files: 1
skills_used: []
---

# T02: MessageBus and SSE tests

1. Create tests/test_message_bus.py
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

## Inputs

- `src/mcp_agent_factory/messaging/bus.py`
- `src/mcp_agent_factory/messaging/sse_router.py`

## Expected Output

- `tests/test_message_bus.py`

## Verification

python -m pytest tests/test_message_bus.py -v
