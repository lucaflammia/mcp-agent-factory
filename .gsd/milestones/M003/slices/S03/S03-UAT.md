# S03: Async Message Bus + SSE Transport — UAT

**Milestone:** M003
**Written:** 2026-03-27T10:57:45.898Z

## UAT: Message Bus\n\n```python\nimport asyncio\nfrom mcp_agent_factory.messaging.bus import MessageBus, AgentMessage\n\nasync def main():\n    bus = MessageBus()\n    q = bus.subscribe(\"pipeline.events\")\n    msg = AgentMessage(topic=\"pipeline.events\", sender=\"analyst\", content={\"step\": \"done\"})\n    bus.publish(\"pipeline.events\", msg)\n    received = await q.get()\n    print(f\"Received: {received.sender} \u2192 {received.content}\")\n\nasyncio.run(main())\n```\n\n## UAT: SSE Endpoint (manual)\n```bash\n# Start gateway with SSE router mounted\nuvicorn mcp_agent_factory.gateway.app:gateway_app --port 8002\ncurl -N http://localhost:8002/events?topic=pipeline.events\n```
