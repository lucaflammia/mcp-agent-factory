# M012: Live Demonstration — AI Agents at Work

**Vision:** Bridge code completeness to presentational reliability: wire the existing MCP agent stack into a scripted, zero-touch live demo narrative that proves Privacy-First RAG, full OTel observability, and live provider switching to an audience — without friction.

## Success Criteria

- ./demo.sh runs all three demo phases end-to-end without manual intervention
- Jaeger at :16686 shows Gateway → AnalystAgent → LibrarianAgent → VectorStore span chain with token count attributes
- agents/analyze JSON-RPC method returns real analysis result from local PDF
- Provider switch demo: -32602 error on missing key names the exact key required
- Contract test green: response shape, -32602, and -32603 all verified

## Slices

- [x] **S01: S01** `risk:high` `depends:[]`
  > After this: curl to :8000/mcp with agents/analyze returns a real DocumentAnalysisResult; contract test green validating -32602 on missing provider key and -32603 on pipeline failure

- [x] **S02: S02** `risk:medium` `depends:[]`
  > After this: Jaeger at :16686 shows mcp.agents/analyze with 4 child spans each carrying token count attributes

- [x] **S03: S03** `risk:low` `depends:[]`
  > After this: ./demo.sh runs Phase 1 (locked data), Phase 2 (Jaeger trace), Phase 3 (provider switch with -32602) without manual intervention

## Boundary Map

### S01 → S02

Produces:
- `gateway/app.py` → `_agents_dispatch()` handling all `agents/*` methods
- `gateway/app.py` → `mcp.agents/analyze` root OTel span at dispatch entry
- `tests/test_agents_dispatch.py` → contract test covering response shape, -32602, -32603

Consumes:
- nothing (first slice)

### S01 → S03

Produces:
- `agents/analyze` endpoint reachable at `:8000/mcp` with `MCP_DEV_MODE=1`
- Verified: real `DocumentAnalysisResult` from local PDF

Consumes:
- nothing (first slice)

### S02 → S03

Produces:
- `agents/analyst.py` → 4 child spans with `input_tokens` / `output_tokens` attributes
- Verified: Jaeger shows full Gateway → VectorStore chain

Consumes from S01:
- `mcp.agents/analyze` root span as parent context for child spans
