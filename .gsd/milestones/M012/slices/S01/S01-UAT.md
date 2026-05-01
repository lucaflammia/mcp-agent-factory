# S01: agents/analyze Dispatch — UAT

**Milestone:** M012
**Written:** 2026-05-01T14:46:22.126Z

# S01 UAT: agents/analyze Dispatch\n\n## Test 1: Happy path\n- POST /mcp with method=agents/analyze and MCP_DEV_MODE=1\n- Expected: result dict with summary, provider, input_tokens, output_tokens\n- Status: PASS (contract test)\n\n## Test 2: Missing provider key (-32602)\n- LLM_PROVIDER=openai with no OPENAI_API_KEY set\n- Expected: error.code=-32602, message contains OPENAI_API_KEY\n- Status: PASS (contract test)\n\n## Test 3: Pipeline failure (-32603)\n- analyze_document raises RuntimeError\n- Expected: error.code=-32603\n- Status: PASS (contract test)
