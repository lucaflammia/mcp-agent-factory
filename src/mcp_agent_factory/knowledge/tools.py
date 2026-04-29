"""
Knowledge base query tool — retrieves top-k relevant chunks for a query.
"""
from __future__ import annotations

from mcp_agent_factory.knowledge.embedder import Embedder
from mcp_agent_factory.knowledge.vector_store import VectorStore

try:
    from opentelemetry import trace as _otel_trace
    def _get_tracer(): return _otel_trace.get_tracer("mcp_knowledge")
except ImportError:
    class _NoOpSpan:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def set_attribute(self, *_): pass
    class _FallbackTracer:
        def start_as_current_span(self, *_, **__): return _NoOpSpan()
    _fallback = _FallbackTracer()
    def _get_tracer(): return _fallback


def query_knowledge_base(
	query: str,
	owner_id: str,
	store: VectorStore,
	embedder: Embedder,
	top_k: int = 5,
) -> list[dict]:
	"""Embed *query* and return the top-k matching chunks for *owner_id*.

	Returns a list of dicts with ``text`` and ``score`` keys.
	"""
	tracer = _get_tracer()
	with tracer.start_as_current_span("knowledge.query") as span:
		span.set_attribute("knowledge.owner_id", owner_id)
		span.set_attribute("knowledge.top_k", top_k)
		try:
			query_vector = embedder.embed(query)
			results = store.search(owner_id, query_vector, top_k)
			span.set_attribute("knowledge.result_count", len(results))
			return [{"text": text, "score": score} for text, score in results]
		except Exception as exc:
			span.record_exception(exc)
			try:
				from opentelemetry.trace import StatusCode
				span.set_status(StatusCode.ERROR, str(exc))
			except ImportError:
				pass
			raise
