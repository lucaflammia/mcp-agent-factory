---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T02: Implement _agents_dispatch() and wire into _mcp_dispatch_inner()

Add _agents_dispatch() function in gateway/app.py that handles agents/analyze: validates provider config, builds DocumentAnalysisTask from params, calls AnalystAgent().analyze_document(), and returns a JSON-serializable result dict. Wire it via elif method.startswith('agents/') in _mcp_dispatch_inner(). agents/analyze requires auth (same as tools/call). Unknown agents/* methods return -32601.

## Inputs

- `DocumentAnalysisTask/DocumentAnalysisResult from analyst.py`
- `_mcp_dispatch_inner() branch structure`

## Expected Output

- `_agents_dispatch() function`
- `elif method.startswith('agents/') branch in _mcp_dispatch_inner()`

## Verification

Sending agents/analyze via TestClient with MCP_DEV_MODE=1 returns a result with summary, provider, input_tokens, output_tokens fields.
