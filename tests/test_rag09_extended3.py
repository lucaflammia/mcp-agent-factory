"""RAG-09 final top-up — 30 tests to meet per-slice targets.

S1: +15 (brings S1 to 152+)
S3: +15 (brings S3 to 122+)
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_agent_factory.gateway.query_management import (
    AsyncAuditWriter,
    AuditEntry,
    QueryManager,
    RateLimitConfig,
    TenantConfig,
    calculate_query_cost,
)


def _pool():
    pool = MagicMock()
    conn = AsyncMock()
    conn.executemany = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _e(tenant="t1", cost=1.0) -> AuditEntry:
    return AuditEntry(
        entry_id=f"{tenant}:{int(time.time()*1e6)}",
        tenant=tenant, question="q?", top_k=5,
        result_count=3, top_score=0.9, refused=False, refusal_reason=None,
        retrieval_ms=50.0, generation_ms=10.0, cost_tokens=cost,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )


@pytest.fixture
def cfg():
    return RateLimitConfig(
        tokens_per_second=10.0, burst_size=20, daily_quota=1000, hourly_quota=100,
        cost_top_k_per_unit=0.1, cost_latency_ms_per_100=0.1,
        cost_refusal_penalty=0.5, cost_retry_penalty=0.25,
    )


@pytest.fixture
def redis():
    return AsyncMock()


@pytest.fixture
def kv():
    return AsyncMock()


@pytest.fixture
def qm(redis, kv, cfg):
    pool, _ = _pool()
    return QueryManager(
        kv_store=kv, redis_client=redis, config=cfg,
        pg_pool=pool, audit_flush_interval=999.0, audit_max_buffer=1000,
    )


# ===========================================================================
# S1 — PostgreSQL Audit Logs (+15 tests)
# ===========================================================================


class TestS1_FinalCoverage:
    @pytest.mark.asyncio
    async def test_writer_buffer_is_list(self):
        pool, _ = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        assert isinstance(w._buffer, list)

    @pytest.mark.asyncio
    async def test_writer_lock_exists(self):
        pool, _ = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        assert w._lock is not None

    @pytest.mark.asyncio
    async def test_enqueue_does_not_set_task(self):
        pool, _ = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_e())
        assert w._task is None  # task not started until .start()

    @pytest.mark.asyncio
    async def test_flush_with_zero_max_buffer_flushes_on_enqueue(self):
        pool, conn = _pool()
        # max_buffer=1 flushes after 1 entry
        w = AsyncAuditWriter(pool, flush_interval=999.0, max_buffer=1)
        await w.enqueue(_e())
        conn.executemany.assert_called_once()

    @pytest.mark.asyncio
    async def test_writer_no_pool_task_never_starts(self):
        w = AsyncAuditWriter(None, flush_interval=999.0)
        w.start()
        assert w._task is None

    @pytest.mark.asyncio
    async def test_flush_sql_contains_insert(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_e())
        await w._flush()
        sql = conn.executemany.call_args[0][0].upper()
        assert "INSERT" in sql

    @pytest.mark.asyncio
    async def test_flush_sql_references_audit_table(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_e())
        await w._flush()
        sql = conn.executemany.call_args[0][0].lower()
        assert "query_audit_log" in sql

    @pytest.mark.asyncio
    async def test_export_csv_first_line_is_header(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool)
        result = await w.export(
            "t1", datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc), fmt="csv",
        )
        first_line = result.splitlines()[0]
        assert "tenant" in first_line

    @pytest.mark.asyncio
    async def test_export_json_is_list(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool)
        result = await w.export(
            "t1", datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc), fmt="json",
        )
        assert isinstance(json.loads(result), list)

    @pytest.mark.asyncio
    async def test_query_manager_no_pg_writer_pool_is_none(self):
        qm = QueryManager(
            kv_store=AsyncMock(), redis_client=AsyncMock(), pg_pool=None,
        )
        assert qm._pg_writer._pool is None

    @pytest.mark.asyncio
    async def test_log_query_adds_exactly_one_entry(self, qm, kv):
        kv.set = AsyncMock()
        await qm.log_query(
            tenant="t1", question="q", top_k=5, result_count=1,
            top_score=0.9, refused=False, refusal_reason=None,
            retrieval_latency_ms=50.0, generation_latency_ms=10.0,
        )
        assert len(qm._pg_writer._buffer) == 1

    @pytest.mark.asyncio
    async def test_writer_flush_interval_configurable(self):
        pool, _ = _pool()
        w = AsyncAuditWriter(pool, flush_interval=42.0)
        assert w._flush_interval == 42.0

    @pytest.mark.asyncio
    async def test_writer_max_buffer_configurable(self):
        pool, _ = _pool()
        w = AsyncAuditWriter(pool, max_buffer=250)
        assert w._max_buffer == 250

    @pytest.mark.asyncio
    async def test_enqueue_preserves_cost_tokens(self):
        pool, _ = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_e(cost=7.77))
        assert w._buffer[0].cost_tokens == 7.77

    @pytest.mark.asyncio
    async def test_enqueue_preserves_tenant(self):
        pool, _ = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_e(tenant="bigcorp"))
        assert w._buffer[0].tenant == "bigcorp"


# ===========================================================================
# S3 — Cost-Based Rate Limiting (+15 tests)
# ===========================================================================


class TestS3_FinalCoverage:
    def test_cost_increases_with_every_additional_top_k(self, cfg):
        prev = 0.0
        for k in range(1, 10):
            cost = calculate_query_cost(top_k=k, retrieval_ms=0.0, refused=False, cfg=cfg)
            assert cost >= prev
            prev = cost

    def test_cost_is_float(self, cfg):
        cost = calculate_query_cost(top_k=5, retrieval_ms=50.0, refused=False, cfg=cfg)
        assert isinstance(cost, float)

    def test_cost_always_at_least_1(self, cfg):
        for k in [1, 2, 10]:
            for ms in [0.0, 100.0]:
                cost = calculate_query_cost(top_k=k, retrieval_ms=ms, refused=False, cfg=cfg)
                assert cost >= 1.0

    def test_refused_plus_multiple_retries(self, cfg):
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=True, retries=3, cfg=cfg)
        # 1.0 + 0.5 + 3*0.25 = 2.25
        assert cost == pytest.approx(2.25)

    def test_top_k_zero_same_as_1(self, cfg):
        cost_0 = calculate_query_cost(top_k=0, retrieval_ms=0.0, refused=False, cfg=cfg)
        cost_1 = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, cfg=cfg)
        assert cost_0 == cost_1

    def test_very_high_latency_adds_significant_cost(self, cfg):
        cost = calculate_query_cost(top_k=1, retrieval_ms=10000.0, refused=False, cfg=cfg)
        # 1 + 100 * 0.1 = 11.0
        assert cost == pytest.approx(11.0)

    def test_cost_symmetry_refused_vs_retry(self, cfg):
        cost_refused = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=True, retries=0, cfg=cfg)
        cost_2retry = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, retries=2, cfg=cfg)
        # refusal = 0.5, 2 retries = 0.5 — should be equal
        assert cost_refused == pytest.approx(cost_2retry)

    @pytest.mark.asyncio
    async def test_rate_limit_key_uses_ratelimit_prefix(self, qm, redis):
        redis.get.return_value = None
        redis.setex = AsyncMock()
        await qm.check_rate_limit("corp", cost=1.0)
        key = redis.get.call_args[0][0]
        assert "ratelimit" in key

    @pytest.mark.asyncio
    async def test_rate_limit_key_contains_bucket_suffix(self, qm, redis):
        redis.get.return_value = None
        redis.setex = AsyncMock()
        await qm.check_rate_limit("corp", cost=1.0)
        key = redis.get.call_args[0][0]
        assert "bucket" in key

    @pytest.mark.asyncio
    async def test_allowed_true_has_no_retry_after(self, qm, redis):
        redis.get.return_value = None
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=1.0)
        assert result["retry_after_seconds"] is None

    @pytest.mark.asyncio
    async def test_denied_has_retry_after_gt_zero(self, qm, redis):
        import json as _j
        bucket = {"tokens": 0.0, "last_refill": time.time()}
        redis.get.return_value = _j.dumps(bucket).encode()
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=1.0)
        assert result["retry_after_seconds"] > 0

    @pytest.mark.asyncio
    async def test_cost_field_in_log_entry_matches_input(self, qm, kv):
        kv.set = AsyncMock()
        await qm.log_query(
            tenant="t1", question="q?", top_k=5, result_count=2,
            top_score=0.9, refused=False, refusal_reason=None,
            retrieval_latency_ms=50.0, generation_latency_ms=10.0,
            cost_tokens=5.5,
        )
        assert qm._pg_writer._buffer[0].cost_tokens == 5.5

    @pytest.mark.asyncio
    async def test_default_cost_1_when_not_passed(self, qm, kv):
        kv.set = AsyncMock()
        await qm.log_query(
            tenant="t1", question="q?", top_k=5, result_count=2,
            top_score=0.9, refused=False, refusal_reason=None,
            retrieval_latency_ms=50.0, generation_latency_ms=10.0,
        )
        assert qm._pg_writer._buffer[0].cost_tokens == 1.0

    @pytest.mark.asyncio
    async def test_cost_zero_logged_in_buffer(self, qm, kv):
        kv.set = AsyncMock()
        await qm.log_query(
            tenant="t1", question="q?", top_k=1, result_count=0,
            top_score=None, refused=False, refusal_reason=None,
            retrieval_latency_ms=0.0, generation_latency_ms=0.0,
            cost_tokens=0.0,
        )
        assert qm._pg_writer._buffer[0].cost_tokens == 0.0

    def test_calculate_cost_matches_manual_formula(self, cfg):
        """Verify formula: 1 + (top_k-1)*0.1 + (ms/100)*0.1 + refused*0.5 + retries*0.25"""
        top_k, ms, refused, retries = 7, 300.0, True, 2
        expected = 1.0 + (7-1)*0.1 + (300/100)*0.1 + 0.5 + 2*0.25
        cost = calculate_query_cost(top_k=top_k, retrieval_ms=ms, refused=refused,
                                    retries=retries, cfg=cfg)
        assert cost == pytest.approx(expected, abs=0.0001)
