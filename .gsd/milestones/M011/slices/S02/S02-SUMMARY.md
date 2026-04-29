---
id: S02
parent: M011
milestone: M011
provides:
  - (none)
requires:
  []
affects:
  []
key_files:
  - ["tests/test_otel_spans.py", "tests/test_m011_otel_integration.py", "src/mcp_agent_factory/gateway/telemetry.py", "src/mcp_agent_factory/gateway/service_layer.py", "src/mcp_agent_factory/knowledge/tools.py"]
key_decisions:
  - ["Module-level TracerProvider+InMemorySpanExporter required because OTEL SDK forbids overriding global provider after first set — use autouse fixture to clear between tests"]
patterns_established:
  - ["InMemorySpanExporter pattern for in-process OTEL span testing: set provider once at module level, clear exporter per test via autouse fixture"]
observability_surfaces:
  - ["Jaeger UI at localhost:16686 — mcp-gateway service with mcp.tools/call, tool.{name}, and knowledge.query spans visible after any request"]
drill_down_paths:
  []
duration: ""
verification_result: passed
completed_at: 2026-04-29T04:51:28.445Z
blocker_discovered: false
---

# S02: OpenTelemetry instrumentation

**OTEL tracing is fully wired end-to-end: gateway spans export to Jaeger, unit tests verify span hierarchy in-process, integration tests confirm live traces appear in Jaeger UI.**

## What Happened

All instrumentation code existed from S01 (telemetry.py, gateway _mcp_dispatch span, service_layer tool.{name} span, knowledge.query span, Dockerfile otel extras, Jaeger docker-compose service). S02 added the test coverage to prove it. T01 created 6 unit tests using InMemorySpanExporter — covering idempotency, span names, attributes, and parent-child relationships — with a module-level provider pattern to work around OTEL SDK's single-set-provider constraint. T02 confirmed 353 non-integration tests pass. T03 confirmed all 3 integration tests pass against the live stack: mcp-gateway registers in Jaeger, mcp.tools/call span carries mcp.tool attribute, and tool.add is correctly parented under mcp.tools/call.

## Verification

pytest tests/test_otel_spans.py -v → 6 passed; pytest tests/ -m 'not integration' → 353 passed; pytest tests/test_m011_otel_integration.py -m integration → 3 passed

## Requirements Advanced

None.

## Requirements Validated

None.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

None.

## Follow-ups

None.

## Files Created/Modified

- `tests/test_otel_spans.py` — New: 6 unit tests for OTEL span emission using InMemorySpanExporter
