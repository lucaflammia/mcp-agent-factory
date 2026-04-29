---
estimated_steps: 1
estimated_files: 3
skills_used: []
---

# T01: Implement GeminiHandler and provider_factory

Add GeminiHandler to router.py using httpx. Add provider_factory() that re-reads LLM_PROVIDER per call. Add file_context_extractor MCP tool using pypdf.

## Inputs

- `src/mcp_agent_factory/gateway/router.py`

## Expected Output

- `GeminiHandler class`
- `provider_factory function`
- `file_context_extractor tool`

## Verification

pytest tests/ -q --tb=no -k "gemini or provider" 2>&1 | tail -3

## Observability Impact

EventLog warning on missing GEMINI_API_KEY
