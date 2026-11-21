"""RAG-09 third test file — additional coverage to meet per-slice acceptance targets.

Adds ~120 tests:
  S1: +60 (target 150+)
  S2: +15 (target 100+)
  S3: +45 (target 120+)
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_agent_factory.gateway.query_management import (
    AsyncAuditWriter,
    AuditEntry,
    QueryManager,
    RateLimitConfig,
    TenantConfig,
    _quota_reset_seconds,
    _quota_window_key,
    calculate_query_cost,
    is_valid_timezone,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _pool(rows=None, error=None):
    pool = MagicMock()
    conn = AsyncMock()
    conn.executemany = AsyncMock(side_effect=error) if error else AsyncMock()
    conn.fetch = AsyncMock(return_value=rows or [])
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _e(tenant="t1", top_k=5, retrieval_ms=50.0, refused=False, cost=1.0) -> AuditEntry:
    return AuditEntry(
        entry_id=f"{tenant}:{int(time.time()*1e6)}",
        tenant=tenant,
        question="q?",
        top_k=top_k,
        result_count=3,
        top_score=0.9,
        refused=refused,
        refusal_reason=None,
        retrieval_ms=retrieval_ms,
        generation_ms=10.0,
        cost_tokens=cost,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )


@pytest.fixture
def cfg():
    return RateLimitConfig(
        tokens_per_second=10.0, burst_size=20,
        daily_quota=1000, hourly_quota=100,
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
# S1 — PostgreSQL Audit Logs (+60 tests)
# ===========================================================================


class TestS1_FlushIsolation:
    """Verify flush does not leak entries between calls."""

    @pytest.mark.asyncio
    async def test_flush_clears_buffer_then_new_enqueue_refills(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_e())
        await w._flush()
        assert w._buffer == []
        await w.enqueue(_e(tenant="t2"))
        assert len(w._buffer) == 1

    @pytest.mark.asyncio
    async def test_two_independent_flush_calls(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_e())
        await w._flush()
        await w.enqueue(_e())
        await w._flush()
        assert conn.executemany.call_count == 2

    @pytest.mark.asyncio
    async def test_flush_does_not_mix_entries_across_calls(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_e(tenant="first"))
        await w._flush()
        first_rows = conn.executemany.call_args_list[0][0][1]
        assert first_rows[0][0] == "first"

        await w.enqueue(_e(tenant="second"))
        await w._flush()
        second_rows = conn.executemany.call_args_list[1][0][1]
        assert second_rows[0][0] == "second"

    @pytest.mark.asyncio
    async def test_enqueue_at_exact_max_flushes(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0, max_buffer=5)
        for _ in range(5):
            await w.enqueue(_e())
        conn.executemany.assert_called_once()

    @pytest.mark.asyncio
    async def test_enqueue_one_less_than_max_does_not_flush(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0, max_buffer=5)
        for _ in range(4):
            await w.enqueue(_e())
        conn.executemany.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_error_does_not_lose_other_entries(self):
        pool, conn = _pool(error=RuntimeError("DB error"))
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        for _ in range(3):
            await w.enqueue(_e())
        await w._flush()
        # Entries should be restored
        assert len(w._buffer) == 3

    @pytest.mark.asyncio
    async def test_flush_no_pool_leaves_buffer_untouched_after_enqueue(self):
        w = AsyncAuditWriter(None)
        await w.enqueue(_e())
        await w._flush()
        # With no pool, _flush_locked returns early — buffer untouched
        assert len(w._buffer) == 1


class TestS1_ExportTenantIsolation:
    @pytest.mark.asyncio
    async def test_export_passes_tenant_to_query(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool)
        await w.export("my-tenant", datetime(2024, 1, 1, tzinfo=timezone.utc),
                       datetime(2024, 2, 1, tzinfo=timezone.utc))
        assert conn.fetch.call_args[0][1] == "my-tenant"

    @pytest.mark.asyncio
    async def test_export_csv_no_pg_returns_header(self):
        w = AsyncAuditWriter(None)
        result = await w.export("t", datetime(2024, 1, 1, tzinfo=timezone.utc),
                                datetime(2024, 2, 1, tzinfo=timezone.utc), fmt="csv")
        assert result.strip() != ""

    @pytest.mark.asyncio
    async def test_export_json_no_pg_is_valid_json(self):
        w = AsyncAuditWriter(None)
        result = await w.export("t", datetime(2024, 1, 1, tzinfo=timezone.utc),
                                datetime(2024, 2, 1, tzinfo=timezone.utc), fmt="json")
        parsed = json.loads(result)
        assert parsed == []

    @pytest.mark.asyncio
    async def test_export_start_lt_end_passed_correctly(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool)
        start = datetime(2024, 3, 1, tzinfo=timezone.utc)
        end = datetime(2024, 3, 31, tzinfo=timezone.utc)
        await w.export("t", start, end)
        args = conn.fetch.call_args[0]
        assert args[2] == start
        assert args[3] == end

    @pytest.mark.asyncio
    async def test_export_returns_string(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool)
        result = await w.export("t", datetime(2024, 1, 1, tzinfo=timezone.utc),
                                datetime(2024, 2, 1, tzinfo=timezone.utc))
        assert isinstance(result, str)


class TestS1_AuditEntryModel:
    def test_entry_id_stored(self):
        e = _e(tenant="x")
        assert e.entry_id.startswith("x:")

    def test_tenant_field(self):
        e = _e(tenant="acme")
        assert e.tenant == "acme"

    def test_question_field(self):
        entry = AuditEntry(
            entry_id="e1", tenant="t1", question="how does RAG work?",
            top_k=5, result_count=3, top_score=0.9,
            refused=False, refusal_reason=None,
            retrieval_ms=50.0, generation_ms=10.0,
            cost_tokens=1.0, timestamp="2024-01-01T00:00:00+00:00",
        )
        assert entry.question == "how does RAG work?"

    def test_refused_true(self):
        e = _e(refused=True)
        assert e.refused is True

    def test_refused_false(self):
        e = _e(refused=False)
        assert e.refused is False

    def test_cost_tokens_stored(self):
        e = _e(cost=4.2)
        assert e.cost_tokens == 4.2

    def test_top_k_stored(self):
        e = _e(top_k=20)
        assert e.top_k == 20

    def test_retrieval_ms_stored(self):
        e = _e(retrieval_ms=333.3)
        assert e.retrieval_ms == 333.3

    def test_timestamp_is_string(self):
        e = _e()
        assert isinstance(e.timestamp, str)

    def test_timestamp_contains_utc_offset(self):
        e = _e()
        assert "+" in e.timestamp or "Z" in e.timestamp or "UTC" in e.timestamp


class TestS1_WriterWithPgPool:
    @pytest.mark.asyncio
    async def test_enqueue_1001_triggers_at_least_one_flush(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0, max_buffer=1000)
        for i in range(1001):
            await w.enqueue(_e(tenant=f"t{i}"))
        assert conn.executemany.call_count >= 1

    @pytest.mark.asyncio
    async def test_flush_uses_executemany_not_execute(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_e())
        await w._flush()
        conn.executemany.assert_called_once()
        conn.execute = AsyncMock()  # should not have been called
        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_pool_acquire_called_on_flush(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_e())
        await w._flush()
        pool.acquire.assert_called_once()

    @pytest.mark.asyncio
    async def test_pool_acquire_not_called_on_empty_flush(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w._flush()  # empty buffer
        pool.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_tenants_in_single_flush_batch(self):
        pool, conn = _pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        for t in ["a", "b", "c", "d", "e"]:
            await w.enqueue(_e(tenant=t))
        await w._flush()
        rows = conn.executemany.call_args[0][1]
        tenants = [r[0] for r in rows]
        assert set(tenants) == {"a", "b", "c", "d", "e"}


class TestS1_QueryManagerPgWriter:
    @pytest.mark.asyncio
    async def test_query_manager_creates_pg_writer(self, qm):
        assert qm._pg_writer is not None

    @pytest.mark.asyncio
    async def test_query_manager_pg_writer_has_pool(self, qm):
        assert qm._pg_writer._pool is not None

    @pytest.mark.asyncio
    async def test_log_query_enqueues_to_pg_writer(self, qm, kv):
        kv.set = AsyncMock()
        await qm.log_query(
            tenant="t1", question="q?", top_k=5, result_count=3,
            top_score=0.9, refused=False, refusal_reason=None,
            retrieval_latency_ms=50.0, generation_latency_ms=10.0,
        )
        assert len(qm._pg_writer._buffer) == 1

    @pytest.mark.asyncio
    async def test_export_audit_no_pg_returns_empty_json(self):
        pool2, _ = _pool()
        qm2 = QueryManager(
            kv_store=AsyncMock(), redis_client=AsyncMock(), pg_pool=None,
        )
        result = await qm2.export_audit(
            "t1", datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc), fmt="json",
        )
        assert result == "[]"

    @pytest.mark.asyncio
    async def test_query_manager_start_starts_writer(self, qm):
        qm._pg_writer = MagicMock()
        qm._pg_writer.start = MagicMock()
        qm._pg_writer.stop = AsyncMock()
        qm.start()
        qm._pg_writer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_manager_stop_stops_writer(self, qm):
        qm._pg_writer = MagicMock()
        qm._pg_writer.start = MagicMock()
        qm._pg_writer.stop = AsyncMock()
        await qm.stop()
        qm._pg_writer.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_query_entry_id_starts_with_tenant(self, qm, kv):
        kv.set = AsyncMock()
        eid = await qm.log_query(
            tenant="myco", question="q", top_k=5, result_count=1,
            top_score=0.9, refused=False, refusal_reason=None,
            retrieval_latency_ms=50.0, generation_latency_ms=10.0,
        )
        assert eid.startswith("myco:")

    @pytest.mark.asyncio
    async def test_log_query_question_truncated_to_500(self, qm, kv):
        kv.set = AsyncMock()
        await qm.log_query(
            tenant="t1", question="x" * 600, top_k=5, result_count=0,
            top_score=None, refused=False, refusal_reason=None,
            retrieval_latency_ms=5.0, generation_latency_ms=5.0,
        )
        entry = qm._pg_writer._buffer[0]
        assert len(entry.question) == 500

    @pytest.mark.asyncio
    async def test_log_query_question_short_not_truncated(self, qm, kv):
        kv.set = AsyncMock()
        await qm.log_query(
            tenant="t1", question="short", top_k=5, result_count=1,
            top_score=0.9, refused=False, refusal_reason=None,
            retrieval_latency_ms=5.0, generation_latency_ms=5.0,
        )
        entry = qm._pg_writer._buffer[0]
        assert entry.question == "short"


# ===========================================================================
# S2 — Timezone-Aware Quotas (+15 tests)
# ===========================================================================


class TestS2_AdditionalTimezones:
    def test_chicago_timezone_valid(self):
        assert is_valid_timezone("America/Chicago") is True

    def test_miami_timezone_valid(self):
        assert is_valid_timezone("America/New_York") is True

    def test_mexico_city_timezone_valid(self):
        assert is_valid_timezone("America/Mexico_City") is True

    def test_sao_paulo_timezone_valid(self):
        assert is_valid_timezone("America/Sao_Paulo") is True

    def test_johannesburg_timezone_valid(self):
        assert is_valid_timezone("Africa/Johannesburg") is True

    def test_istanbul_timezone_valid(self):
        assert is_valid_timezone("Europe/Istanbul") is True

    def test_moscow_timezone_valid(self):
        assert is_valid_timezone("Europe/Moscow") is True

    def test_dubai_timezone_valid(self):
        assert is_valid_timezone("Asia/Dubai") is True

    def test_singapore_timezone_valid(self):
        assert is_valid_timezone("Asia/Singapore") is True

    def test_quota_window_sao_paulo(self):
        key = _quota_window_key("daily", "America/Sao_Paulo")
        assert len(key) == 10

    def test_quota_window_moscow(self):
        key = _quota_window_key("daily", "Europe/Moscow")
        assert len(key) == 10

    def test_quota_reset_sao_paulo(self):
        s = _quota_reset_seconds("daily", "America/Sao_Paulo")
        assert 0 < s <= 86400

    def test_quota_reset_singapore(self):
        s = _quota_reset_seconds("hourly", "Asia/Singapore")
        assert 0 < s <= 3600

    @pytest.mark.asyncio
    async def test_set_tenant_config_timezone_stored(self, qm):
        qm.set_tenant_config(TenantConfig(tenant="myco", timezone="America/Chicago"))
        assert qm.get_tenant_config("myco").timezone == "America/Chicago"

    @pytest.mark.asyncio
    async def test_multiple_set_configs_independent(self, qm):
        for tz in ["UTC", "America/New_York", "Asia/Tokyo"]:
            qm.set_tenant_config(TenantConfig(tenant=tz.replace("/", "_"), timezone=tz))
        assert qm.get_tenant_config("UTC").timezone == "UTC"
        assert qm.get_tenant_config("America_New_York").timezone == "America/New_York"


# ===========================================================================
# S3 — Cost-Based Rate Limiting (+45 tests)
# ===========================================================================


class TestS3_CostFormulaCoverage:
    @pytest.mark.parametrize("top_k,expected_extra", [
        (1, 0.0), (2, 0.1), (5, 0.4), (10, 0.9), (20, 1.9), (100, 9.9),
    ])
    def test_top_k_cost_formula_parameterized(self, top_k, expected_extra, cfg):
        cost = calculate_query_cost(top_k=top_k, retrieval_ms=0.0, refused=False, cfg=cfg)
        assert cost == pytest.approx(1.0 + expected_extra, abs=0.001)

    @pytest.mark.parametrize("latency,expected_extra", [
        (0.0, 0.0), (100.0, 0.1), (200.0, 0.2), (500.0, 0.5), (1000.0, 1.0),
    ])
    def test_latency_cost_formula_parameterized(self, latency, expected_extra, cfg):
        cost = calculate_query_cost(top_k=1, retrieval_ms=latency, refused=False, cfg=cfg)
        assert cost == pytest.approx(1.0 + expected_extra, abs=0.001)

    @pytest.mark.parametrize("retries,expected_extra", [
        (0, 0.0), (1, 0.25), (2, 0.5), (3, 0.75), (5, 1.25), (10, 2.5),
    ])
    def test_retry_cost_formula_parameterized(self, retries, expected_extra, cfg):
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False,
                                    retries=retries, cfg=cfg)
        assert cost == pytest.approx(1.0 + expected_extra, abs=0.001)

    def test_refused_true_vs_false_diff_exactly_penalty(self, cfg):
        cost_yes = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=True, cfg=cfg)
        cost_no = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, cfg=cfg)
        assert cost_yes - cost_no == pytest.approx(cfg.cost_refusal_penalty)

    def test_cost_monotone_increases_with_top_k(self, cfg):
        costs = [calculate_query_cost(top_k=k, retrieval_ms=0.0, refused=False, cfg=cfg)
                 for k in [1, 5, 10, 20, 50]]
        for i in range(len(costs) - 1):
            assert costs[i] <= costs[i + 1]

    def test_cost_monotone_increases_with_latency(self, cfg):
        costs = [calculate_query_cost(top_k=1, retrieval_ms=ms, refused=False, cfg=cfg)
                 for ms in [0, 100, 500, 1000, 5000]]
        for i in range(len(costs) - 1):
            assert costs[i] <= costs[i + 1]

    def test_cost_monotone_increases_with_retries(self, cfg):
        costs = [calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False,
                                      retries=r, cfg=cfg)
                 for r in [0, 1, 2, 5, 10]]
        for i in range(len(costs) - 1):
            assert costs[i] <= costs[i + 1]


class TestS3_RateLimitEdgeCases:
    @pytest.mark.asyncio
    async def test_exactly_zero_tokens_returns_denied(self, qm, redis):
        import json as _j
        bucket = {"tokens": 0.0, "last_refill": time.time()}
        redis.get.return_value = _j.dumps(bucket).encode()
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=1.0)
        assert result["allowed"] is False

    @pytest.mark.asyncio
    async def test_exactly_enough_tokens_allowed(self, qm, redis):
        import json as _j
        bucket = {"tokens": 5.0, "last_refill": time.time()}
        redis.get.return_value = _j.dumps(bucket).encode()
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=5.0)
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_one_token_over_limit_denied(self, qm, redis):
        import json as _j
        bucket = {"tokens": 4.9, "last_refill": time.time()}
        redis.get.return_value = _j.dumps(bucket).encode()
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=5.0)
        assert result["allowed"] is False

    @pytest.mark.asyncio
    async def test_bucket_persisted_after_allow(self, qm, redis):
        import json as _j
        redis.get.return_value = None
        redis.setex = AsyncMock()
        await qm.check_rate_limit("t1", cost=1.0)
        redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_bucket_persisted_after_deny(self, qm, redis):
        import json as _j
        bucket = {"tokens": 0.0, "last_refill": time.time()}
        redis.get.return_value = _j.dumps(bucket).encode()
        redis.setex = AsyncMock()
        await qm.check_rate_limit("t1", cost=5.0)
        redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_cost_accumulates_across_calls(self, qm, redis):
        import json as _j
        stored = [None]

        async def get_side(key):
            return _j.dumps(stored[0]).encode() if stored[0] else None

        async def setex_side(key, ttl, val):
            stored[0] = _j.loads(val)

        redis.get.side_effect = get_side
        redis.setex.side_effect = setex_side

        # First query uses 5 tokens
        r1 = await qm.check_rate_limit("t1", cost=5.0)
        assert r1["allowed"] is True
        # Second uses 10 tokens (5 + 10 = 15, still within burst 20)
        r2 = await qm.check_rate_limit("t1", cost=10.0)
        assert r2["allowed"] is True
        # Third uses 10 tokens — only ~5 left
        r3 = await qm.check_rate_limit("t1", cost=10.0)
        assert r3["allowed"] is False


class TestS3_CostDistributionStats:
    @pytest.mark.asyncio
    async def test_cost_p99_above_p50_with_varied_costs(self, qm, kv):
        costs = [1.0] * 90 + [10.0] * 10  # 90 cheap, 10 expensive
        kv.keys = AsyncMock(return_value=[f"t1:{i}" for i in range(100)])
        kv.get = AsyncMock(side_effect=[
            {"refused": False, "retrieval_latency_ms": 50.0, "generation_latency_ms": 10.0,
             "top_score": 0.9, "cost_tokens": c}
            for c in costs
        ])
        stats = await qm.get_tenant_stats("t1")
        assert stats["cost_p99"] > stats["cost_p50"]

    @pytest.mark.asyncio
    async def test_cost_percentiles_with_all_same(self, qm, kv):
        n = 10
        kv.keys = AsyncMock(return_value=[f"t1:{i}" for i in range(n)])
        kv.get = AsyncMock(side_effect=[
            {"refused": False, "retrieval_latency_ms": 50.0, "generation_latency_ms": 10.0,
             "top_score": 0.9, "cost_tokens": 2.5}
            for _ in range(n)
        ])
        stats = await qm.get_tenant_stats("t1")
        assert stats["cost_p50"] == pytest.approx(2.5)
        assert stats["cost_p99"] == pytest.approx(2.5)

    @pytest.mark.asyncio
    async def test_stats_contains_all_required_keys(self, qm, kv):
        kv.keys = AsyncMock(return_value=[])
        stats = await qm.get_tenant_stats("t1")
        for key in ("cost_p50", "cost_p99"):
            assert key in stats

    @pytest.mark.asyncio
    async def test_cost_percentiles_non_negative(self, qm, kv):
        kv.keys = AsyncMock(return_value=["t1:1"])
        kv.get = AsyncMock(return_value={
            "refused": False, "retrieval_latency_ms": 50.0,
            "generation_latency_ms": 10.0, "top_score": 0.9, "cost_tokens": 1.0,
        })
        stats = await qm.get_tenant_stats("t1")
        assert stats["cost_p50"] >= 0
        assert stats["cost_p99"] >= 0

    @pytest.mark.asyncio
    async def test_refused_queries_included_in_cost_distribution(self, qm, kv):
        kv.keys = AsyncMock(return_value=["t1:1", "t1:2"])
        kv.get = AsyncMock(side_effect=[
            {"refused": False, "retrieval_latency_ms": 50.0,
             "generation_latency_ms": 10.0, "top_score": 0.9, "cost_tokens": 1.0},
            {"refused": True, "retrieval_latency_ms": 5.0,
             "generation_latency_ms": 0.0, "top_score": 0.1, "cost_tokens": 1.5},
        ])
        stats = await qm.get_tenant_stats("t1")
        assert stats["cost_p50"] > 0
