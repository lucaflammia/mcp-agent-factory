# S02: OpenTelemetry instrumentation

**Goal:** Add in-process unit tests for OTEL span emission and verify a real query_knowledge_base request produces a complete trace visible in Jaeger.
**Demo:** Send one query_knowledge_base request; Jaeger UI at localhost:16686 shows a complete trace with child spans

## Must-Haves

- pytest tests/test_otel_spans.py passes without Docker; integration test confirms mcp-gateway service + mcp.tools/call span + knowledge.query child span appear in Jaeger.

## Proof Level

- This slice proves: Not provided.

## Integration Closure

Not provided.

## Verification

- Unit tests use InMemorySpanExporter to assert span names, attributes, and parent-child relationships without a live collector. Integration tests confirm OTLP export to Jaeger works end-to-end.

## Tasks

- [x] **T01: Unit tests for OTEL spans (InMemorySpanExporter)** `est:30m`
  Write tests/test_otel_spans.py using opentelemetry-sdk's InMemorySpanExporter to assert: (1) configure_telemetry() is idempotent with OTEL_TRACES_EXPORTER=none, (2) _mcp_dispatch sets mcp.method and mcp.tool attributes, (3) service_layer.handle() emits a tool.{name} child span, (4) knowledge.query span is emitted with owner_id and result_count attributes. Tests must run without Docker via OTEL_TRACES_EXPORTER=none + a real TracerProvider wired to InMemorySpanExporter.
  - Files: `tests/test_otel_spans.py`, `src/mcp_agent_factory/gateway/telemetry.py`
  - Verify: pytest tests/test_otel_spans.py -v exits 0

- [x] **T02: Full test suite regression check** `est:10m`
  Run the full pytest suite (excluding integration markers) to confirm no regressions from the telemetry wiring added in S01.
  - Verify: pytest tests/ -m 'not integration' -v exits 0

- [x] **T03: Live stack verification — Jaeger trace confirmation** `est:15m`
  With docker compose --profile full up running (MCP_DEV_MODE=1), run the integration tests and manually confirm: mcp-gateway appears in Jaeger services list, a mcp.tools/call span exists with mcp.tool=echo, and a tool.echo child span exists under it.
  - Files: `tests/test_m011_otel_integration.py`
  - Verify: pytest tests/test_m011_otel_integration.py -m integration -v exits 0

## Files Likely Touched

- tests/test_otel_spans.py
- src/mcp_agent_factory/gateway/telemetry.py
- tests/test_m011_otel_integration.py
