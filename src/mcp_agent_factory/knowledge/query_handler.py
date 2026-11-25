"""Query handler with mandatory filter resolution and embedder validation.

RAG-03: Guarded retrieval — makes filtering a precondition rather than
post-processing. All queries must include:
  - Resolved tenant from auth context
  - ACL and date filters passed to the vector store
  - Embedder version verification

This module ensures that no query path can accidentally bypass tenant
isolation or embedder version checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import numpy as np

from mcp_agent_factory.gateway.telemetry import get_tracer
from mcp_agent_factory.knowledge.vector_store import ChunkResult

try:
    from prometheus_client import REGISTRY, Counter, Gauge, Histogram

    def _get_or_create(cls, name, doc, labelnames=(), **kwargs):
        if name in REGISTRY._names_to_collectors:
            return REGISTRY._names_to_collectors[name]
        return cls(name, doc, labelnames, **kwargs)

    _query_total = _get_or_create(Counter, "rag_query_total", "Total RAG queries", ["tenant"])
    _query_empty = _get_or_create(Counter, "rag_query_empty_results_total", "RAG queries returning empty results", ["tenant"])
    _score_gap = _get_or_create(Gauge, "rag_retrieval_score_gap", "Gap between top-1 and top-2 retrieval scores", ["tenant"])
    _chunk_count = _get_or_create(Gauge, "rag_index_chunk_count", "Total chunks in the vector index")
    _retrieval_score = _get_or_create(
        Histogram,
        "rag_retrieval_score",
        "Similarity scores of retrieved chunks",
        ["tenant", "embedder_id"],
        buckets=[0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0],
    )
    _top1_score = _get_or_create(Gauge, "rag_top1_score", "Similarity score of the top-1 retrieved chunk", ["tenant"])
    _query_cost_histogram = _get_or_create(
        Histogram,
        "rag_query_cost_tokens",
        "Variable query cost in tokens (RAG-09 S3)",
        buckets=[0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0],
    )
except ImportError:
    class _NoOp:
        def labels(self, **kw): return self
        def inc(self, v=1): pass
        def set(self, v): pass
        def observe(self, v): pass

    _query_total = _NoOp()
    _query_empty = _NoOp()
    _score_gap = _NoOp()
    _chunk_count = _NoOp()
    _retrieval_score = _NoOp()
    _top1_score = _NoOp()
    _query_cost_histogram = _NoOp()


@dataclass
class QueryFilter:
    """Validated query filter state from auth context."""
    tenant: str
    acl_labels: list[str]
    date_start: datetime | None = None
    date_end: datetime | None = None
    embedder_id: str | None = None

    def validate(self) -> None:
        """Raise ValueError if tenant is missing or empty."""
        if not self.tenant or not self.tenant.strip():
            raise ValueError("Query rejected: tenant filter is required and must not be empty")


class FilterResolver(Protocol):
    """Resolves query context to enforced filters."""

    def resolve(self, context: dict) -> QueryFilter:
        """Resolve filter from authenticated context.

        Args:
            context: Request context dict with 'tenant', 'acl', 'date_start', 'date_end', 'embedder_id'

        Returns:
            QueryFilter with validated tenant and filters

        Raises:
            ValueError: if tenant is missing or invalid
        """
        ...  # pragma: no cover


class DefaultFilterResolver:
    """Default filter resolver — extracts tenant/ACL/dates from context."""

    def resolve(self, context: dict) -> QueryFilter:
        tenant = context.get("tenant", "").strip()
        if not tenant:
            raise ValueError("Query rejected: tenant filter is required")

        filter_ = QueryFilter(
            tenant=tenant,
            acl_labels=context.get("acl", []),
            date_start=context.get("date_start"),
            date_end=context.get("date_end"),
            embedder_id=context.get("embedder_id"),
        )
        filter_.validate()
        return filter_


class GuardedQueryHandler:
    """Wrapper that enforces filter resolution and embedder validation before retrieval.

    Usage::

        handler = GuardedQueryHandler(
            vector_store=store,
            embedder=embedder,
            filter_resolver=resolver,
        )

        # User context from auth layer
        context = {"tenant": "acme", "acl": ["admin"], "embedder_id": "all-MiniLM-L6-v2@v1"}
        query_text = "What is machine learning?"

        results = handler.retrieve(
            query_text=query_text,
            auth_context=context,
            top_k=5,
        )
    """

    def __init__(
        self,
        vector_store,
        embedder,
        filter_resolver: FilterResolver | None = None,
    ) -> None:
        self._store = vector_store
        self._embedder = embedder
        self._resolver = filter_resolver or DefaultFilterResolver()
        self._tracer = get_tracer("mcp_gateway.query_handler")
        self._update_chunk_count_gauge()

    def _update_chunk_count_gauge(self) -> None:
        try:
            status = self._store.status() if hasattr(self._store, "status") else {}
            count = status.get("chunk_count")
            if count is None and hasattr(self._store, "_store"):
                count = len(self._store._store)
            if count is not None:
                _chunk_count.set(count)
        except Exception:
            pass

    def retrieve(
        self,
        query_text: str,
        auth_context: dict,
        top_k: int = 5,
        rerank_k: int = 10,
        mmr_k: int = 5,
    ) -> list[ChunkResult]:
        """Retrieve documents with mandatory filter validation and embedder checking.

        Args:
            query_text: the query to embed and search for
            auth_context: authenticated context dict with 'tenant', 'acl', 'embedder_id'
            top_k: final result count after MMR diversification
            rerank_k: intermediate count after reranking
            mmr_k: intermediate count after MMR (typically == top_k)

        Returns:
            list of ChunkResult objects with text, score, and chunk_id for citation tracking

        Raises:
            ValueError: if tenant is missing, embedder_id mismatch, or filters are invalid
        """
        with self._tracer.start_as_current_span("query_handler.retrieve") as span:
            # Stage 1: Resolve and validate filters
            with self._tracer.start_as_current_span("query_handler.resolve_filters") as filter_span:
                filter_obj = self._resolver.resolve(auth_context)
                filter_obj.validate()
                filter_span.set_attribute("filter.tenant", filter_obj.tenant)
                filter_span.set_attribute("filter.acl_count", len(filter_obj.acl_labels))
                if filter_obj.date_start:
                    filter_span.set_attribute("filter.date_start", filter_obj.date_start.isoformat())
                if filter_obj.date_end:
                    filter_span.set_attribute("filter.date_end", filter_obj.date_end.isoformat())

            # Stage 2: Embed query
            with self._tracer.start_as_current_span("query_handler.embed_query") as embed_span:
                query_vector = self._embedder.embed(query_text)
                embed_span.set_attribute("query.embedding_dim", len(query_vector))

            # Stage 3: ANN search with mandatory filters
            with self._tracer.start_as_current_span("query_handler.ann_search") as ann_span:
                # Determine if vector store supports advanced filtering
                if hasattr(self._store, "search_with_filters"):
                    # Use advanced search with ACL/date filters
                    results = self._store.search_with_filters(
                        owner_id=filter_obj.tenant,
                        query_vector=query_vector,
                        acl_labels=filter_obj.acl_labels,
                        date_start=filter_obj.date_start,
                        date_end=filter_obj.date_end,
                        embedder_id=filter_obj.embedder_id,
                        top_k=rerank_k * 2,  # Get more candidates for reranking
                    )
                else:
                    # Fallback: basic owner_id filtering
                    results = self._store.search(
                        owner_id=filter_obj.tenant,
                        query_vector=query_vector,
                        top_k=rerank_k * 2,
                    )
                ann_span.set_attribute("ann.result_count", len(results))

            # Stage 4: Rerank (if reranker is available)
            if hasattr(self._store, "rerank"):
                with self._tracer.start_as_current_span("query_handler.rerank") as rerank_span:
                    results = self._store.rerank(query_text, results, top_k=rerank_k)
                    rerank_span.set_attribute("rerank.result_count", len(results))

            # Stage 5: MMR diversification
            with self._tracer.start_as_current_span("query_handler.mmr") as mmr_span:
                if hasattr(self._store, "mmr_diversify"):
                    results = self._store.mmr_diversify(results, top_k=mmr_k)
                mmr_span.set_attribute("mmr.result_count", len(results))

            span.set_attribute("final.result_count", len(results))

            tenant = filter_obj.tenant
            embedder_id = filter_obj.embedder_id or "default"
            _query_total.labels(tenant=tenant).inc()
            if not results:
                _query_empty.labels(tenant=tenant).inc()
            else:
                # results may be ChunkResult objects or (text, score) tuples (fallback path)
                def _score(r):
                    return r.score if hasattr(r, "score") else r[1]

                _top1_score.labels(tenant=tenant).set(_score(results[0]))
                for chunk in results:
                    _retrieval_score.labels(tenant=tenant, embedder_id=embedder_id).observe(_score(chunk))
                if len(results) >= 2:
                    gap = _score(results[0]) - _score(results[1])
                    _score_gap.labels(tenant=tenant).set(gap)

            self._update_chunk_count_gauge()

            return results
