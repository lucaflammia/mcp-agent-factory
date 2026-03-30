---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T01: Extend MCPGatewayClient + add __main__

Add stream_events() async method to MCPGatewayClient that opens /sse/v1/events and yields parsed AgentMessage dicts. Add debug logging around list_tools and call_tool. Add __main__ module to bridge package.

## Inputs

- `src/mcp_agent_factory/bridge/gateway_client.py`
- `src/mcp_agent_factory/bridge/oauth_middleware.py`

## Expected Output

- `src/mcp_agent_factory/bridge/gateway_client.py`
- `src/mcp_agent_factory/bridge/__main__.py`

## Verification

python -c "from mcp_agent_factory.bridge.gateway_client import MCPGatewayClient; assert hasattr(MCPGatewayClient, 'stream_events')"
