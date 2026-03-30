---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T01: Add gateway/run.py and mcp.json

Create gateway/run.py with uvicorn.run(gateway_app) on 0.0.0.0:8000. Create gateway/__main__.py to support python -m mcp_agent_factory.gateway.run. Write mcp.json at project root with serverUrl, authUrl, endpoints, and tool descriptions.

## Inputs

- `src/mcp_agent_factory/gateway/app.py`

## Expected Output

- `src/mcp_agent_factory/gateway/run.py`
- `mcp.json`

## Verification

python -c "import mcp_agent_factory.gateway.run" && python -c "import json; json.load(open('mcp.json'))"
