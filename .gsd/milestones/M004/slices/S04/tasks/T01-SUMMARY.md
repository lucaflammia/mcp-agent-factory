---
id: T01
parent: S04
milestone: M004
provides: []
requires: []
affects: []
key_files: ["src/mcp_agent_factory/gateway/run.py", "mcp.json"]
key_decisions: ["mcp.json includes auth server on :8001 separate from gateway on :8000 — matches real deployment where auth server and resource server run as separate processes"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "import check + JSON validation both pass"
completed_at: 2026-03-30T06:53:49.481Z
blocker_discovered: false
---

# T01: gateway/run.py and mcp.json created for external client connectivity

> gateway/run.py and mcp.json created for external client connectivity

## What Happened
---
id: T01
parent: S04
milestone: M004
key_files:
  - src/mcp_agent_factory/gateway/run.py
  - mcp.json
key_decisions:
  - mcp.json includes auth server on :8001 separate from gateway on :8000 — matches real deployment where auth server and resource server run as separate processes
duration: ""
verification_result: passed
completed_at: 2026-03-30T06:53:49.481Z
blocker_discovered: false
---

# T01: gateway/run.py and mcp.json created for external client connectivity

**gateway/run.py and mcp.json created for external client connectivity**

## What Happened

Created run.py with uvicorn.run() reading HOST/PORT/LOG_LEVEL/RELOAD from env. Created mcp.json at project root with full tool schema, auth config (PKCE S256), and endpoint map for Cursor/Claude Desktop.

## Verification

import check + JSON validation both pass

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -c "import mcp_agent_factory.gateway.run" && python -c "import json; json.load(open('mcp.json'))"` | 0 | ✅ pass | 600ms |


## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/mcp_agent_factory/gateway/run.py`
- `mcp.json`


## Deviations
None.

## Known Issues
None.
