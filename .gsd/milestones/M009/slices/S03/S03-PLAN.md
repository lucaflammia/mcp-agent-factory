# S03: Context Pruner with Cosine Filtering

**Goal:** Implement ContextPruner that filters retrieved knowledge chunks by cosine similarity before they reach the LLM, with env-var-configurable threshold and safe empty-context fallthrough.
**Demo:** Vector chunk with cosine similarity below threshold is dropped; on-topic chunk passes; empty-context fallthrough proceeds without error

## Must-Haves

- `ContextPruner.prune(query, chunks, embedder, threshold)` in `gateway/pruner.py` drops chunks below threshold and returns on-topic chunks
- Empty chunk list input returns empty list without error
- Threshold readable from `MCP_CONTEXT_THRESHOLD` env var (default 0.3)
- ContextPruner wired into `query_knowledge_base` path in `service_layer.py`
- Unit tests: below-threshold chunk dropped, on-topic chunk passes, empty-context fallthrough, env-var threshold override
- Full test suite passes with 0 regressions

## Proof Level

- This slice proves: - This slice proves: contract + integration (real numpy cosine math, StubEmbedder, wired into service_layer query path)
- Real runtime required: no (StubEmbedder sufficient)
- Human/UAT required: no

## Integration Closure

- Upstream surfaces consumed: `Embedder` protocol from `knowledge/embedder.py`; `StubEmbedder` for tests; `InternalServiceLayer.query_knowledge_base` branch in `service_layer.py`
- New wiring introduced: `ContextPruner` called in service_layer after `query_knowledge_base()` retrieval, before result is returned
- What remains before end-to-end usable: S05 live docker-compose + Caddy stack wiring; S04 async cache + token.usage events

## Verification

- Runtime signals: none added (pruner is synchronous, in-process)
- Inspection surfaces: unit tests show dropped vs. kept chunks
- Failure visibility: empty list returned on all-prune; no exception surfaced to caller
- Redaction constraints: chunk text is user-owned knowledge; not logged

## Tasks

- [ ] **T01: Implement ContextPruner in gateway/pruner.py** `est:30m`
  Build ContextPruner class with prune(query, chunks, embedder, threshold) method. Reads threshold from MCP_CONTEXT_THRESHOLD env var when not supplied explicitly (default 0.3). Computes cosine similarity between embedded query and each chunk embedding; drops chunks below threshold. Returns empty list safely when all chunks fall below threshold or input is empty.
  - Files: `src/mcp_agent_factory/gateway/pruner.py`, `src/mcp_agent_factory/knowledge/embedder.py`
  - Verify: python -c "from mcp_agent_factory.gateway.pruner import ContextPruner; print('import ok')"

- [ ] **T02: Write unit tests for ContextPruner and wire into service_layer query_knowledge_base path** `est:45m`
  Write tests/test_m009_s03.py covering: (1) below-threshold chunk is dropped, (2) above-threshold chunk passes, (3) empty chunk list returns empty with no error, (4) MCP_CONTEXT_THRESHOLD env var overrides default threshold. Then wire ContextPruner into the query_knowledge_base branch of InternalServiceLayer.handle() — call pruner after query_knowledge_base() returns, before building the outcome. Run full suite to confirm 0 regressions.
  - Files: `tests/test_m009_s03.py`, `src/mcp_agent_factory/gateway/service_layer.py`
  - Verify: python -m pytest tests/test_m009_s03.py -v && python -m pytest --tb=short -q 2>&1 | tail -5

## Files Likely Touched

- src/mcp_agent_factory/gateway/pruner.py
- src/mcp_agent_factory/knowledge/embedder.py
- tests/test_m009_s03.py
- src/mcp_agent_factory/gateway/service_layer.py
