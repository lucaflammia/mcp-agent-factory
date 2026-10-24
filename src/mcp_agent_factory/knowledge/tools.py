"""Knowledge base query tool — retrieves top-k relevant chunks for a query."""
from __future__ import annotations

from mcp_agent_factory.knowledge.embedder import Embedder
from mcp_agent_factory.knowledge.reranker import NoOpReranker, Reranker
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
  reranker: Reranker | None = None,
  use_hybrid: bool = False,
) -> list[dict]:
  """Embed *query* and return the top-k matching chunks for *owner_id*.

  Args:
      use_hybrid: If True and *store* supports search_hybrid(), uses dense +
                  full-text RRF fusion before reranking. Falls back to dense-only
                  if the store does not expose search_hybrid.
      reranker:   Optional cross-encoder reranker. Defaults to NoOpReranker
                  (score-order truncation). Pass CrossEncoderReranker to enable.

  Returns a list of dicts with ``text`` and ``score`` keys.
  """
  if reranker is None:
    reranker = NoOpReranker()

  tracer = _get_tracer()
  with tracer.start_as_current_span("knowledge.query") as span:
    span.set_attribute("knowledge.owner_id", owner_id)
    span.set_attribute("knowledge.top_k", top_k)
    span.set_attribute("knowledge.hybrid", use_hybrid)
    try:
      query_vector = embedder.embed(query)
      candidate_k = max(top_k * 10, 50)

      if use_hybrid and hasattr(store, "search_hybrid"):
        results = store.search_hybrid(owner_id, query, query_vector, top_k=candidate_k)
      else:
        results = store.search(owner_id, query_vector, top_k=candidate_k)

      reranked = reranker.rerank(query, results, top_k=top_k)
      span.set_attribute("knowledge.result_count", len(reranked))
      return [{"text": text, "score": score} for text, score in reranked]
    except Exception as exc:
      span.record_exception(exc)
      try:
        from opentelemetry.trace import StatusCode
        span.set_status(StatusCode.ERROR, str(exc))
      except ImportError:
        pass
      raise
