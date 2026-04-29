"""
Unit tests for OpenTelemetry span emission — no live collector required.

Each test wires a fresh TracerProvider + InMemorySpanExporter, sets it as
the global provider, exercises the code under test, then asserts on the
captured spans.  The global provider is restored after every test.
"""
from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry", reason="opentelemetry-sdk not installed")

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# OTEL SDK only allows set_tracer_provider() once per process — subsequent
# calls are silently ignored with a warning.  Wire the exporter once at module
# level and clear it between tests instead.
_EXPORTER = InMemorySpanExporter()
_PROVIDER = TracerProvider()
_PROVIDER.add_span_processor(SimpleSpanProcessor(_EXPORTER))
trace.set_tracer_provider(_PROVIDER)


@pytest.fixture(autouse=True)
def span_exporter():
    """Clear the shared exporter before each test and yield it."""
    _EXPORTER.clear()
    yield _EXPORTER


def _span_names(exporter: InMemorySpanExporter) -> list[str]:
    return [s.name for s in exporter.get_finished_spans()]


def _span_attrs(exporter: InMemorySpanExporter, name: str) -> dict:
    for s in exporter.get_finished_spans():
        if s.name == name:
            return dict(s.attributes or {})
    raise KeyError(f"No span named {name!r} found in {_span_names(exporter)}")


# ---------------------------------------------------------------------------
# telemetry.configure_telemetry() idempotency
# ---------------------------------------------------------------------------

def test_configure_telemetry_none_exporter(monkeypatch):
    """configure_telemetry() with OTEL_TRACES_EXPORTER=none must not crash and
    must be idempotent (calling twice is safe)."""
    import mcp_agent_factory.gateway.telemetry as tel
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setattr(tel, "_configured", False)
    tel.configure_telemetry()
    tel.configure_telemetry()  # second call — no-op
    assert tel._configured is True


def test_get_tracer_returns_noop_when_not_configured(monkeypatch):
    """get_tracer() must return a working tracer even when called before configure_telemetry."""
    import mcp_agent_factory.gateway.telemetry as tel
    tracer = tel.get_tracer("test")
    # Must be usable as a context manager
    with tracer.start_as_current_span("test-span") as span:
        span.set_attribute("x", 1)


# ---------------------------------------------------------------------------
# service_layer spans
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_layer_emits_tool_span(span_exporter):
    """service_layer.handle('echo') must emit a tool.echo span with tool.name attribute."""
    from unittest.mock import AsyncMock, MagicMock
    from mcp_agent_factory.gateway.service_layer import InternalServiceLayer
    from mcp_agent_factory.messaging.bus import MessageBus

    bus = MessageBus()
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    sampling = MagicMock()
    vector_store = MagicMock()
    embedder = MagicMock()
    event_log = MagicMock()
    event_log.append = AsyncMock()

    svc = InternalServiceLayer(bus, session, sampling, vector_store, embedder, event_log)
    result = await svc.handle("echo", {"text": "hello"}, claims=None)

    assert result["content"][0]["text"] == "hello"
    names = _span_names(span_exporter)
    assert "tool.echo" in names, f"Expected tool.echo in {names}"
    attrs = _span_attrs(span_exporter, "tool.echo")
    assert attrs.get("tool.name") == "echo"


@pytest.mark.asyncio
async def test_service_layer_emits_add_span(span_exporter):
    """service_layer.handle('add') must emit a tool.add span."""
    from unittest.mock import AsyncMock, MagicMock
    from mcp_agent_factory.gateway.service_layer import InternalServiceLayer
    from mcp_agent_factory.messaging.bus import MessageBus

    bus = MessageBus()
    session = MagicMock()
    sampling = MagicMock()
    vector_store = MagicMock()
    embedder = MagicMock()
    event_log = MagicMock()
    event_log.append = AsyncMock()

    svc = InternalServiceLayer(bus, session, sampling, vector_store, embedder, event_log)
    result = await svc.handle("add", {"a": 3, "b": 4}, claims=None)

    assert result["content"][0]["text"] == "7"
    assert "tool.add" in _span_names(span_exporter)


# ---------------------------------------------------------------------------
# knowledge.query span
# ---------------------------------------------------------------------------

def test_knowledge_query_emits_span(span_exporter):
    """query_knowledge_base() must emit a knowledge.query span with owner_id and result_count."""
    import numpy as np
    from unittest.mock import MagicMock
    from mcp_agent_factory.knowledge.tools import query_knowledge_base

    embedder = MagicMock()
    embedder.embed.return_value = np.zeros(384)

    store = MagicMock()
    store.search.return_value = [("chunk one", 0.9), ("chunk two", 0.7)]

    results = query_knowledge_base("test query", "user-123", store, embedder, top_k=2)

    assert len(results) == 2
    names = _span_names(span_exporter)
    assert "knowledge.query" in names, f"Expected knowledge.query in {names}"
    attrs = _span_attrs(span_exporter, "knowledge.query")
    assert attrs.get("knowledge.owner_id") == "user-123"
    assert attrs.get("knowledge.top_k") == 2
    assert attrs.get("knowledge.result_count") == 2


# ---------------------------------------------------------------------------
# Parent-child span relationship
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_span_is_child_of_caller_span(span_exporter):
    """When handle() is called inside an outer span, tool.echo must be its child."""
    from unittest.mock import AsyncMock, MagicMock
    from mcp_agent_factory.gateway.service_layer import InternalServiceLayer
    from mcp_agent_factory.messaging.bus import MessageBus

    bus = MessageBus()
    session = MagicMock()
    sampling = MagicMock()
    vector_store = MagicMock()
    embedder = MagicMock()
    event_log = MagicMock()
    event_log.append = AsyncMock()

    svc = InternalServiceLayer(bus, session, sampling, vector_store, embedder, event_log)

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("mcp.tools/call") as parent_span:
        await svc.handle("echo", {"text": "nested"}, claims=None)

    spans = {s.name: s for s in span_exporter.get_finished_spans()}
    assert "tool.echo" in spans
    assert "mcp.tools/call" in spans

    parent_ctx = spans["mcp.tools/call"].context
    child_parent_id = spans["tool.echo"].parent.span_id
    assert child_parent_id == parent_ctx.span_id, (
        f"tool.echo parent span_id {child_parent_id!r} != "
        f"mcp.tools/call span_id {parent_ctx.span_id!r}"
    )
