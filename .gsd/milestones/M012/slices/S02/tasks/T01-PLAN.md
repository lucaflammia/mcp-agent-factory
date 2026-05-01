---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T01: Add OTel child spans to AnalystAgent.analyze_document()

Instrument AnalystAgent.analyze_document() with 4 child spans under the active trace context: agent.pdf_extract (wraps LibrarianAgent.extract call), agent.prune (wraps ContextPruner.prune), agent.pii_scrub (wraps PIIGate.scrub), agent.llm_route (wraps UnifiedRouter.route). Each span records input_tokens and output_tokens as attributes using values from DocumentAnalysisResult telemetry fields. Spans must propagate the parent context from the gateway's mcp.agents/analyze span.

## Inputs

- `S01 mcp.agents/analyze root span`
- `DocumentAnalysisResult telemetry fields (input_tokens, output_tokens)`

## Expected Output

- `AnalystAgent.analyze_document() emits 4 OTel child spans`
- `Each span has input_tokens and output_tokens attributes`
- `Existing tests still pass`

## Verification

Run pytest tests/test_agents_dispatch.py -v; instrument a manual curl with MCP_DEV_MODE=1 against the running stack and verify Jaeger shows 4 child spans under mcp.agents/analyze.
