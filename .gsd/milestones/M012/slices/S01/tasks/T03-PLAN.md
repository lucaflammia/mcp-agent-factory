---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T03: Write contract test for agents/analyze dispatch

Create tests/test_agents_dispatch.py with three test cases: (1) happy path — monkeypatch AnalystAgent.analyze_document to return a stub DocumentAnalysisResult, verify response has result dict with correct fields; (2) -32602 — set LLM_PROVIDER=openai with no OPENAI_API_KEY, verify error code -32602 and message names the key; (3) -32603 — monkeypatch analyze_document to raise RuntimeError, verify error code -32603. All tests use MCP_DEV_MODE=1.

## Inputs

- `gateway/app.py _agents_dispatch() implementation`
- `existing gateway test patterns in tests/`

## Expected Output

- `tests/test_agents_dispatch.py with 3 green tests`

## Verification

pytest tests/test_agents_dispatch.py -v → 3 tests green
