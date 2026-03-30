---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T02: Write tests/test_m004_client_bridge.py

Write tests/test_m004_client_bridge.py: list_tools via ASGITransport, call_tool echo, token cache (same token returned on second call), token refresh on near-expiry, SSE stream subscription test.

## Inputs

- `src/mcp_agent_factory/bridge/gateway_client.py`
- `src/mcp_agent_factory/gateway/app.py`

## Expected Output

- `tests/test_m004_client_bridge.py`

## Verification

pytest tests/test_m004_client_bridge.py -v
