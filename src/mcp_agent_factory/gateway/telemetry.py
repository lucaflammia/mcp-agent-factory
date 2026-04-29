"""OpenTelemetry setup for the MCP gateway.

Call ``configure_telemetry()`` once at application startup.  The function is
idempotent — subsequent calls are no-ops so tests that import the module
multiple times stay safe.

Environment variables (all optional):
  OTEL_SERVICE_NAME        default: mcp-gateway
  OTEL_EXPORTER_OTLP_ENDPOINT  default: http://localhost:4317
  OTEL_TRACES_EXPORTER     set to "none" to disable export (useful in tests)
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_configured = False


def configure_telemetry() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    exporter_type = os.getenv("OTEL_TRACES_EXPORTER", "otlp").lower()
    if exporter_type == "none":
        logger.debug("OTEL tracing disabled (OTEL_TRACES_EXPORTER=none)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    except ImportError:
        logger.warning("opentelemetry packages not installed — tracing disabled")
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "mcp-gateway")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    resource = Resource(attributes={SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrument outbound httpx calls (e.g. OAuth discovery proxy)
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except ImportError:
        pass

    logger.debug("OTEL tracing configured → %s (service: %s)", endpoint, service_name)


def get_tracer(name: str = "mcp_gateway"):
    """Return a tracer, falling back to a no-op tracer when OTEL is not configured."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


class _NoOpSpan:
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def set_attribute(self, *_): pass
    def record_exception(self, *_): pass
    def set_status(self, *_): pass


class _NoOpTracer:
    def start_as_current_span(self, name, **kwargs):
        return _NoOpSpan()
