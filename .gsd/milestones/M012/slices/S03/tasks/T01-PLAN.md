---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T01: Write demo.sh with three-phase execution

Create scripts/demo.sh that: (1) checks docker compose health (all services up, exits with clear message if not); (2) Phase 1 — POST agents/analyze with MCP_DEV_MODE=1 against the local PDF, pretty-prints the DocumentAnalysisResult summary; (3) Phase 2 — prints the Jaeger deep-link URL for the most recent trace (http://localhost:16686/search?service=mcp-gateway); (4) Phase 3 — repeats the agents/analyze call with LLM_PROVIDER=openai and no OPENAI_API_KEY set, shows the -32602 error response side-by-side with Phase 1 output. Uses only curl and jq — no Python dependencies.

## Inputs

- `S01 agents/analyze endpoint at :8000/mcp`
- `S02 Jaeger at :16686`
- `docker compose service names from docker-compose.yml`

## Expected Output

- `scripts/demo.sh is executable and runs all three phases`
- `Phase 1 output: pretty-printed DocumentAnalysisResult`
- `Phase 2 output: Jaeger trace URL`
- `Phase 3 output: -32602 JSON error naming OPENAI_API_KEY`

## Verification

Run ./scripts/demo.sh against a running stack (MCP_DEV_MODE=1); Phase 1 shows analysis result; Phase 2 shows Jaeger URL; Phase 3 shows -32602 error with OPENAI_API_KEY in message.
