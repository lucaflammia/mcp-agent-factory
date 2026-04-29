---
id: T01
parent: S02
milestone: M011
key_files:
  - tests/test_otel_spans.py
key_decisions:
  - Module-level TracerProvider+InMemorySpanExporter pattern required because OTEL SDK forbids overriding the global provider after first set
duration: 
verification_result: passed
completed_at: 2026-04-29T04:50:44.682Z
blocker_discovered: false
---

# T01: 6 unit tests using InMemorySpanExporter verify span names, attributes, and parent-child hierarchy without a live collector

**6 unit tests using InMemorySpanExporter verify span names, attributes, and parent-child hierarchy without a live collector**

## What Happened

Created tests/test_otel_spans.py with 6 tests covering: configure_telemetry idempotency with OTEL_TRACES_EXPORTER=none, get_tracer no-op fallback, service_layer emitting tool.echo and tool.add spans with tool.name attribute, knowledge.query span with owner_id/result_count attributes, and parent-child relationship between mcp.tools/call and tool.echo spans. Key issue: OTEL SDK only allows set_tracer_provider() once per process — subsequent calls log a warning and are ignored. Fixed by using a module-level provider+exporter and clearing the exporter between tests via autouse fixture.

## Verification

pytest tests/test_otel_spans.py -v → 6 passed

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `pytest tests/test_otel_spans.py -v` | 0 | 6 passed | 1120ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `tests/test_otel_spans.py`
