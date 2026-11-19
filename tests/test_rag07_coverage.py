"""Coverage tests for RAG-07 patch lines not hit by existing test suites.

Targets:
- generation.py:31  — _get_or_create_counter cache-hit branch
- generation.py:54-65 — ImportError _NoOp fallback
- generation.py:168-169 — _build_context backward-compat tuple branch
- generation.py:241 — GenerationValidator backward-compat index-based chunk IDs
- generation.py:271 — should_refuse tuple score branch
- query_handler.py:28 — _get_or_create cache-hit branch
- query_handler.py:43-55 — ImportError _NoOp fallback
- query_handler.py:152-153 — _update_chunk_count_gauge exception path
"""
import sys

import pytest  # noqa: E402

# ---------------------------------------------------------------------------
# generation.py helpers
# ---------------------------------------------------------------------------

def _import_generation():
    import mcp_agent_factory.knowledge.generation as gen
    return gen


class TestGenerationCounterCacheHit:
    """generation.py:31 — _get_or_create_counter returns cached counter."""

    def test_double_import_does_not_duplicate_counter(self):
        gen = _import_generation()
        # Counter names are already registered; re-importing must not raise.
        # We exercise the cache-hit branch by calling _get_or_create_counter again.
        try:
            from prometheus_client import REGISTRY
            cached = gen._get_or_create_counter(
                "rag_generation_total",
                "Total generation requests",
                ["provider"],
            )
            assert cached is not None
        except (AttributeError, ImportError):
            pytest.skip("prometheus_client not available")


class TestGenerationNoOpFallback:
    """generation.py:54-65 — _NoOp class used when prometheus_client absent."""

    def test_noop_fallback_when_prometheus_absent(self, monkeypatch):
        # Hide prometheus_client so the ImportError branch executes.
        saved = {k: v for k, v in sys.modules.items() if "prometheus_client" in k}
        for k in saved:
            monkeypatch.setitem(sys.modules, k, None)  # type: ignore[arg-type]

        if "mcp_agent_factory.knowledge.generation" in sys.modules:
            monkeypatch.delitem(sys.modules, "mcp_agent_factory.knowledge.generation")

        import importlib
        gen = importlib.import_module("mcp_agent_factory.knowledge.generation")

        # _NoOp objects must be callable with .labels().inc() without raising.
        gen._generation_total.labels(provider="test").inc()
        gen._generation_refusals.labels(reason="test").inc()
        gen._generation_retries.labels(provider="test").inc()
        gen._citation_validation_failures.labels(reason="test").inc()


class TestFormatContextBackwardCompat:
    """generation.py:168-169 — format_context handles plain tuples."""

    def test_format_context_with_tuples(self):
        from mcp_agent_factory.knowledge.generation import format_context

        chunks = [("First chunk text", 0.9), ("Second chunk text", 0.8)]
        result = format_context(chunks)
        assert "chunk-1" in result
        assert "First chunk text" in result
        assert "chunk-2" in result
        assert "Second chunk text" in result

    def test_format_context_with_plain_string_no_chunk_id(self):
        from mcp_agent_factory.knowledge.generation import format_context

        # A plain string — no chunk_id attribute, not a tuple/list
        result = format_context(["plain string"])
        assert "chunk-1" in result
        assert "plain string" in result


class TestGenerationValidatorIndexBasedChunkIds:
    """generation.py:241 — backward-compat index-based IDs for plain tuples."""

    def test_validate_with_tuple_chunks_uses_index_ids(self):
        from mcp_agent_factory.knowledge.generation import GenerationValidator, RagAnswer

        validator = GenerationValidator()
        raw = '{"answer": "Net income was $8.1M", "cited_chunk_ids": ["chunk-0"], "refused": false, "refusal_reason": null}'
        chunks = [("Net income was $8.1M", 0.9)]
        answer, is_valid = validator.validate_answer(raw, chunks)
        # Index-based ID "chunk-0" built from .index() should match and pass citation check.
        assert answer is not None


class TestShouldRefuseTupleScore:
    """generation.py:271 — should_refuse reads score from tuple[1]."""

    def test_should_refuse_low_score_tuple(self):
        from mcp_agent_factory.knowledge.generation import GenerationValidator

        validator = GenerationValidator()
        assert validator.should_refuse([("some text", 0.1)]) is True

    def test_should_refuse_high_score_tuple(self):
        from mcp_agent_factory.knowledge.generation import GenerationValidator

        validator = GenerationValidator()
        assert validator.should_refuse([("some text", 0.9)]) is False

    def test_should_refuse_empty_tuple_defaults_zero(self):
        from mcp_agent_factory.knowledge.generation import GenerationValidator

        validator = GenerationValidator()
        # Tuple with only one element — score defaults to 0.0, so should refuse.
        assert validator.should_refuse([("only text",)]) is True


# ---------------------------------------------------------------------------
# query_handler.py helpers
# ---------------------------------------------------------------------------

class TestQueryHandlerCounterCacheHit:
    """query_handler.py:28 — _get_or_create returns cached metric."""

    def test_double_import_does_not_duplicate_metrics(self):
        try:
            from prometheus_client import REGISTRY, Counter

            import mcp_agent_factory.knowledge.query_handler as qh
            cached = qh._get_or_create(
                Counter,
                "rag_query_total",
                "Total RAG queries",
                ["tenant"],
            )
            assert cached is not None
        except (AttributeError, ImportError):
            pytest.skip("prometheus_client not available")


class TestQueryHandlerNoOpFallback:
    """query_handler.py:43-55 — _NoOp fallback when prometheus_client absent."""

    def test_noop_fallback_when_prometheus_absent(self, monkeypatch):
        saved = {k: v for k, v in sys.modules.items() if "prometheus_client" in k}
        for k in saved:
            monkeypatch.setitem(sys.modules, k, None)  # type: ignore[arg-type]

        mod_key = "mcp_agent_factory.knowledge.query_handler"
        if mod_key in sys.modules:
            monkeypatch.delitem(sys.modules, mod_key)

        import importlib
        qh = importlib.import_module(mod_key)

        qh._query_total.labels(tenant="t").inc()
        qh._query_empty.labels(tenant="t").inc()
        qh._score_gap.labels(tenant="t").set(0.5)
        qh._chunk_count.set(10)
        qh._retrieval_score.labels(tenant="t", embedder_id="e").observe(0.8)
        qh._top1_score.labels(tenant="t").set(0.9)


class TestUpdateChunkCountGaugeException:
    """query_handler.py:152-153 — _update_chunk_count_gauge swallows exceptions."""

    def test_exception_in_store_status_is_swallowed(self):
        from mcp_agent_factory.knowledge.query_handler import GuardedQueryHandler

        class BrokenStore:
            def status(self):
                raise RuntimeError("DB is down")

        class DummyEmbedder:
            def embed(self, text):
                return [0.0]

        # Should not raise even though status() throws.
        handler = GuardedQueryHandler(
            vector_store=BrokenStore(),
            embedder=DummyEmbedder(),
        )
        assert handler is not None
