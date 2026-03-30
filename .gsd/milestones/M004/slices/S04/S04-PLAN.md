# S04: Launch Script + mcp.json External Config

**Goal:** Add gateway/run.py uvicorn entrypoint and mcp.json at project root for Cursor/Claude Desktop integration.
**Demo:** After this: python -m mcp_agent_factory.gateway.run starts; curl http://localhost:8000/health returns 200; mcp.json is checked in and valid.

## Tasks
- [x] **T01: gateway/run.py and mcp.json created for external client connectivity** — Create gateway/run.py with uvicorn.run(gateway_app) on 0.0.0.0:8000. Create gateway/__main__.py to support python -m mcp_agent_factory.gateway.run. Write mcp.json at project root with serverUrl, authUrl, endpoints, and tool descriptions.
  - Estimate: 20m
  - Files: src/mcp_agent_factory/gateway/run.py, mcp.json
  - Verify: python -c "import mcp_agent_factory.gateway.run" && python -c "import json; json.load(open('mcp.json'))"
- [x] **T02: 198 tests passing; docs updated** — Run the full test suite and update KNOWLEDGE.md and PROJECT.md with M004 lessons and new capabilities.
  - Estimate: 15m
  - Files: .gsd/KNOWLEDGE.md, .gsd/PROJECT.md
  - Verify: pytest tests/ -q --tb=no
