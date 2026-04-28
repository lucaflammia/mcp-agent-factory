---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T02: Write unit tests for ContextPruner and wire into service_layer query_knowledge_base path

Write tests/test_m009_s03.py covering: (1) below-threshold chunk is dropped, (2) above-threshold chunk passes, (3) empty chunk list returns empty with no error, (4) MCP_CONTEXT_THRESHOLD env var overrides default threshold. Then wire ContextPruner into the query_knowledge_base branch of InternalServiceLayer.handle() — call pruner after query_knowledge_base() returns, before building the outcome. Run full suite to confirm 0 regressions.

## Inputs

- `src/mcp_agent_factory/gateway/pruner.py — ContextPruner from T01`
- `src/mcp_agent_factory/gateway/service_layer.py — query_knowledge_base branch to wire pruner into`
- `src/mcp_agent_factory/knowledge/embedder.py — StubEmbedder for test fixture`

## Expected Output

- `tests/test_m009_s03.py — unit + integration tests for ContextPruner`
- `src/mcp_agent_factory/gateway/service_layer.py — ContextPruner wired into query_knowledge_base path`

## Verification

python -m pytest tests/test_m009_s03.py -v && python -m pytest --tb=short -q 2>&1 | tail -5

## Observability Impact

none
