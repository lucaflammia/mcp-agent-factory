# S02: Full OTel Pipeline Instrumentation

**Goal:** Wire OTel child spans into the agent pipeline (PDF extract → prune → PII scrub → LLM route) so Jaeger shows the full Gateway → AnalystAgent → LibrarianAgent → VectorStore chain with input/output token counts on each span.
**Demo:** Jaeger at :16686 shows mcp.agents/analyze with 4 child spans each carrying token count attributes

## Must-Haves

- pytest tests/ -v passes; Jaeger trace for a real agents/analyze call shows agent.pdf_extract, agent.prune, agent.pii_scrub, agent.llm_route child spans each with token count attributes.

## Proof Level

- This slice proves: Jaeger at :16686 shows mcp.agents/analyze root span with 4 named child spans each carrying input_tokens and output_tokens attributes.

## Integration Closure

Consumes the mcp.agents/analyze root OTel span added in S01 as the parent context. Produces child spans that surface during demo Phase 2.

## Verification

- Not provided.

## Tasks

- [x] **T01: Add OTel child spans to AnalystAgent.analyze_document()** `est:45m`
  Instrument AnalystAgent.analyze_document() with 4 child spans under the active trace context: agent.pdf_extract (wraps LibrarianAgent.extract call), agent.prune (wraps ContextPruner.prune), agent.pii_scrub (wraps PIIGate.scrub), agent.llm_route (wraps UnifiedRouter.route). Each span records input_tokens and output_tokens as attributes using values from DocumentAnalysisResult telemetry fields. Spans must propagate the parent context from the gateway's mcp.agents/analyze span.
  - Files: `src/mcp_agent_factory/agents/analyst.py`, `src/mcp_agent_factory/gateway/telemetry.py`
  - Verify: Run pytest tests/test_agents_dispatch.py -v; instrument a manual curl with MCP_DEV_MODE=1 against the running stack and verify Jaeger shows 4 child spans under mcp.agents/analyze.

- [x] **T02: Instrument LibrarianAgent and VectorStore with child spans** `est:30m`
  Add OTel spans to LibrarianAgent.extract() (span: agent.librarian.extract) and VectorStore.search() (span: agent.vector_store.search) so the trace descends to the local data layer. These are leaf spans under agent.pdf_extract and agent.llm_route respectively. No token counts needed here — record document chunk counts and query vector dimension as span attributes instead.
  - Files: `src/mcp_agent_factory/agents/librarian.py`, `src/mcp_agent_factory/knowledge/vector_store.py`
  - Verify: Jaeger trace shows agent.librarian.extract and agent.vector_store.search as leaf spans under mcp.agents/analyze.

## Files Likely Touched

- src/mcp_agent_factory/agents/analyst.py
- src/mcp_agent_factory/gateway/telemetry.py
- src/mcp_agent_factory/agents/librarian.py
- src/mcp_agent_factory/knowledge/vector_store.py
