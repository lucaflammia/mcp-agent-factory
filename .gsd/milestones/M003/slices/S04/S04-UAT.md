# S04: MCP API Gateway + Sampling — UAT

**Milestone:** M003
**Written:** 2026-03-27T11:25:22.179Z

## UAT: MCP API Gateway + Sampling

### Setup
```bash
pip install -e .
python -m pytest tests/test_gateway.py -v
```

### Test Cases

| # | Scenario | Expected | Result |
|---|----------|----------|--------|
| 1 | GET /health (no auth) | 200 `{"status":"ok"}` | ✅ |
| 2 | POST /mcp without token | 401 | ✅ |
| 3 | POST /mcp tools/list with valid JWT | 200 + tools array containing echo | ✅ |
| 4 | POST /mcp tools/call echo with valid JWT | echo text returned | ✅ |
| 5 | POST /mcp tools/call unknown_tool | isError=True | ✅ |
| 6 | POST /sampling {prompt} | SamplingResult with completion | ✅ |
| 7 | Stub completion prefix | starts with [stub] | ✅ |
| 8 | SSE route registered | /sse mount present | ✅ |
| 9 | tools/call publishes to MessageBus | queue non-empty, sender=gateway | ✅ |

All 9 tests passed.

