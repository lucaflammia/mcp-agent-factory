---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T01: Unit tests for OTEL spans (InMemorySpanExporter)

Write tests/test_otel_spans.py using opentelemetry-sdk's InMemorySpanExporter to assert: (1) configure_telemetry() is idempotent with OTEL_TRACES_EXPORTER=none, (2) _mcp_dispatch sets mcp.method and mcp.tool attributes, (3) service_layer.handle() emits a tool.{name} child span, (4) knowledge.query span is emitted with owner_id and result_count attributes. Tests must run without Docker via OTEL_TRACES_EXPORTER=none + a real TracerProvider wired to InMemorySpanExporter.

## Inputs

- `src/mcp_agent_factory/gateway/telemetry.py`
- `src/mcp_agent_factory/gateway/service_layer.py`
- `src/mcp_agent_factory/knowledge/tools.py`

## Expected Output

- `tests/test_otel_spans.py with >=4 passing tests`
- `All assertions on span name, attributes, and hierarchy pass`

## Verification

pytest tests/test_otel_spans.py -v exits 0
