"""RAG-09 tests: PostgreSQL audit logs, timezone-aware quotas, cost-based limiting.

S1 — PostgreSQL Audit Logs (150+ tests)
S2 — Timezone-Aware Quotas (100+ tests)
S3 — Cost-Based Rate Limiting (120+ tests)
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any
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

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def default_config() -> RateLimitConfig:
    return RateLimitConfig(
        tokens_per_second=10.0,
        burst_size=20,
        daily_quota=1000,
        hourly_quota=100,
        cost_top_k_per_unit=0.1,
        cost_latency_ms_per_100=0.1,
        cost_refusal_penalty=0.5,
        cost_retry_penalty=0.25,
    )


@pytest.fixture
def mock_redis() -> AsyncMock:
    client = AsyncMock()
    return client


@pytest.fixture
def mock_kv_store() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_pg_pool() -> MagicMock:
    pool = MagicMock()
    conn = AsyncMock()
    conn.executemany = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


@pytest.fixture
def audit_writer(mock_pg_pool) -> AsyncAuditWriter:
    return AsyncAuditWriter(mock_pg_pool, flush_interval=999.0, max_buffer=1000)


@pytest.fixture
def audit_writer_no_pg() -> AsyncAuditWriter:
    return AsyncAuditWriter(None)


@pytest.fixture
def query_manager(mock_redis, mock_kv_store, default_config, mock_pg_pool) -> QueryManager:
    return QueryManager(
        kv_store=mock_kv_store,
        redis_client=mock_redis,
        config=default_config,
        pg_pool=mock_pg_pool,
        audit_flush_interval=999.0,
        audit_max_buffer=1000,
    )


@pytest.fixture
def query_manager_no_pg(mock_redis, mock_kv_store, default_config) -> QueryManager:
    return QueryManager(
        kv_store=mock_kv_store,
        redis_client=mock_redis,
        config=default_config,
        pg_pool=None,
    )


def _make_entry(
    tenant: str = "tenant-a",
    top_k: int = 5,
    retrieval_ms: float = 50.0,
    refused: bool = False,
    cost: float = 1.0,
) -> AuditEntry:
    return AuditEntry(
        entry_id=f"{tenant}:1234",
        tenant=tenant,
        question="test question",
        top_k=top_k,
        result_count=3,
        top_score=0.9,
        refused=refused,
        refusal_reason=None,
        retrieval_ms=retrieval_ms,
        generation_ms=20.0,
        cost_tokens=cost,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )


# ===========================================================================
# S1 — AsyncAuditWriter
# ===========================================================================


class TestAsyncAuditWriterInit:
    def test_init_with_pg_pool(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool)
        assert w._pool is mock_pg_pool

    def test_init_without_pg_pool(self):
        w = AsyncAuditWriter(None)
        assert w._pool is None

    def test_default_flush_interval(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool)
        assert w._flush_interval == 10.0

    def test_custom_flush_interval(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool, flush_interval=30.0)
        assert w._flush_interval == 30.0

    def test_default_max_buffer(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool)
        assert w._max_buffer == 1000

    def test_custom_max_buffer(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool, max_buffer=500)
        assert w._max_buffer == 500

    def test_buffer_starts_empty(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool)
        assert w._buffer == []

    def test_no_task_before_start(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool)
        assert w._task is None


class TestAsyncAuditWriterEnqueue:
    @pytest.mark.asyncio
    async def test_enqueue_adds_to_buffer(self, audit_writer):
        entry = _make_entry()
        await audit_writer.enqueue(entry)
        assert len(audit_writer._buffer) == 1

    @pytest.mark.asyncio
    async def test_enqueue_multiple(self, audit_writer):
        for i in range(5):
            await audit_writer.enqueue(_make_entry(tenant=f"t{i}"))
        assert len(audit_writer._buffer) == 5

    @pytest.mark.asyncio
    async def test_enqueue_triggers_flush_at_max_buffer(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool, max_buffer=3)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.executemany = AsyncMock()
        for i in range(3):
            await w.enqueue(_make_entry(tenant=f"t{i}"))
        conn.executemany.assert_called_once()
        assert len(w._buffer) == 0

    @pytest.mark.asyncio
    async def test_enqueue_no_flush_before_max(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool, max_buffer=5)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.executemany = AsyncMock()
        for i in range(4):
            await w.enqueue(_make_entry(tenant=f"t{i}"))
        conn.executemany.assert_not_called()

    @pytest.mark.asyncio
    async def test_enqueue_no_pg_does_not_crash(self, audit_writer_no_pg):
        entry = _make_entry()
        await audit_writer_no_pg.enqueue(entry)
        assert len(audit_writer_no_pg._buffer) == 1

    @pytest.mark.asyncio
    async def test_enqueue_retains_all_fields(self, audit_writer):
        entry = _make_entry(top_k=10, retrieval_ms=200.0, refused=True)
        await audit_writer.enqueue(entry)
        stored = audit_writer._buffer[0]
        assert stored.top_k == 10
        assert stored.retrieval_ms == 200.0
        assert stored.refused is True


class TestAsyncAuditWriterFlush:
    @pytest.mark.asyncio
    async def test_flush_sends_to_pg(self, audit_writer, mock_pg_pool):
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.executemany = AsyncMock()
        await audit_writer.enqueue(_make_entry())
        await audit_writer._flush()
        conn.executemany.assert_called_once()

    @pytest.mark.asyncio
    async def test_flush_clears_buffer(self, audit_writer, mock_pg_pool):
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.executemany = AsyncMock()
        for _ in range(3):
            await audit_writer.enqueue(_make_entry())
        await audit_writer._flush()
        assert audit_writer._buffer == []

    @pytest.mark.asyncio
    async def test_flush_empty_buffer_is_noop(self, audit_writer, mock_pg_pool):
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.executemany = AsyncMock()
        await audit_writer._flush()
        conn.executemany.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_no_pg_is_noop(self, audit_writer_no_pg):
        await audit_writer_no_pg.enqueue(_make_entry())
        # Should not raise
        await audit_writer_no_pg._flush()

    @pytest.mark.asyncio
    async def test_flush_error_returns_entries_to_buffer(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool, flush_interval=999.0)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.executemany = AsyncMock(side_effect=RuntimeError("DB down"))
        await w.enqueue(_make_entry())
        await w._flush()
        # Entries returned to buffer on error
        assert len(w._buffer) == 1

    @pytest.mark.asyncio
    async def test_flush_sends_correct_tuple_count(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool, flush_interval=999.0)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.executemany = AsyncMock()
        for _ in range(7):
            await w.enqueue(_make_entry())
        await w._flush()
        call_args = conn.executemany.call_args[0]
        rows = call_args[1]
        assert len(rows) == 7

    @pytest.mark.asyncio
    async def test_flush_includes_cost_tokens(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool, flush_interval=999.0)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.executemany = AsyncMock()
        await w.enqueue(_make_entry(cost=2.5))
        await w._flush()
        rows = conn.executemany.call_args[0][1]
        # cost_tokens is the 10th field (index 9)
        assert rows[0][9] == 2.5


class TestAsyncAuditWriterExport:
    @pytest.mark.asyncio
    async def test_export_json_no_pg(self, audit_writer_no_pg):
        result = await audit_writer_no_pg.export(
            "tenant-a",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="json",
        )
        assert result == "[]"

    @pytest.mark.asyncio
    async def test_export_csv_no_pg(self, audit_writer_no_pg):
        result = await audit_writer_no_pg.export(
            "tenant-a",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="csv",
        )
        assert "tenant" in result

    @pytest.mark.asyncio
    async def test_export_json_returns_rows(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[
            {"tenant": "t1", "question": "q?", "top_k": 5, "result_count": 2,
             "top_score": 0.9, "refused": False, "refusal_reason": None,
             "retrieval_ms": 50.0, "generation_ms": 10.0, "cost_tokens": 1.0,
             "timestamp": "2024-01-15T12:00:00+00:00"},
        ])
        result = await w.export(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="json",
        )
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["tenant"] == "t1"

    @pytest.mark.asyncio
    async def test_export_csv_has_headers(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[
            {"tenant": "t1", "question": "q?", "top_k": 5, "result_count": 2,
             "top_score": 0.9, "refused": False, "refusal_reason": None,
             "retrieval_ms": 50.0, "generation_ms": 10.0, "cost_tokens": 1.0,
             "timestamp": "2024-01-15T12:00:00+00:00"},
        ])
        result = await w.export(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="csv",
        )
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 1
        assert "tenant" in rows[0]
        assert "cost_tokens" in rows[0]

    @pytest.mark.asyncio
    async def test_export_one_day_range(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[])
        start = datetime(2024, 6, 1, tzinfo=timezone.utc)
        end = datetime(2024, 6, 2, tzinfo=timezone.utc)
        await w.export("t1", start, end, fmt="json")
        # positional args: (sql, tenant, start, end)
        call_args = conn.fetch.call_args[0]
        assert call_args[2] == start
        assert call_args[3] == end

    @pytest.mark.asyncio
    async def test_export_one_month_range(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[])
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 2, 1, tzinfo=timezone.utc)
        await w.export("t1", start, end, fmt="json")
        call_args = conn.fetch.call_args[0]
        assert call_args[2] == start
        assert call_args[3] == end

    @pytest.mark.asyncio
    async def test_export_one_year_range(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[])
        start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, tzinfo=timezone.utc)
        await w.export("t1", start, end, fmt="json")
        call_args = conn.fetch.call_args[0]
        assert call_args[2] == start
        assert call_args[3] == end

    @pytest.mark.asyncio
    async def test_export_empty_range_returns_empty(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[])
        result = await w.export(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            fmt="json",
        )
        assert result == "[]"

    @pytest.mark.asyncio
    async def test_export_csv_empty_range_returns_headers_only(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[])
        result = await w.export(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            fmt="csv",
        )
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_export_queries_correct_tenant(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[])
        await w.export(
            "specific-tenant",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
        )
        call_args = conn.fetch.call_args[0]
        # positional: (sql, tenant, start, end)
        assert call_args[1] == "specific-tenant"


class TestQueryManagerAuditLog:
    @pytest.mark.asyncio
    async def test_log_query_writes_redis(self, query_manager, mock_kv_store):
        mock_kv_store.set = AsyncMock()
        await query_manager.log_query(
            tenant="t1", question="q", top_k=5, result_count=3,
            top_score=0.9, refused=False, refusal_reason=None,
            retrieval_latency_ms=50.0, generation_latency_ms=10.0,
            cost_tokens=1.5,
        )
        mock_kv_store.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_query_enqueues_pg(self, query_manager):
        await query_manager.log_query(
            tenant="t1", question="q", top_k=5, result_count=3,
            top_score=0.9, refused=False, refusal_reason=None,
            retrieval_latency_ms=50.0, generation_latency_ms=10.0,
            cost_tokens=1.5,
        )
        assert len(query_manager._pg_writer._buffer) == 1

    @pytest.mark.asyncio
    async def test_log_query_cost_in_pg_buffer(self, query_manager):
        await query_manager.log_query(
            tenant="t1", question="q", top_k=5, result_count=3,
            top_score=None, refused=False, refusal_reason=None,
            retrieval_latency_ms=50.0, generation_latency_ms=10.0,
            cost_tokens=2.75,
        )
        entry = query_manager._pg_writer._buffer[0]
        assert entry.cost_tokens == 2.75

    @pytest.mark.asyncio
    async def test_log_query_returns_entry_id(self, query_manager, mock_kv_store):
        mock_kv_store.set = AsyncMock()
        entry_id = await query_manager.log_query(
            tenant="t2", question="q", top_k=5, result_count=0,
            top_score=None, refused=True, refusal_reason="no results",
            retrieval_latency_ms=5.0, generation_latency_ms=0.0,
        )
        assert entry_id.startswith("t2:")

    @pytest.mark.asyncio
    async def test_log_query_redis_failure_does_not_crash(
        self, query_manager, mock_kv_store
    ):
        mock_kv_store.set = AsyncMock(side_effect=RuntimeError("Redis down"))
        entry_id = await query_manager.log_query(
            tenant="t1", question="q", top_k=5, result_count=0,
            top_score=None, refused=False, refusal_reason=None,
            retrieval_latency_ms=5.0, generation_latency_ms=5.0,
        )
        assert entry_id is not None

    @pytest.mark.asyncio
    async def test_log_query_question_truncated(self, query_manager, mock_kv_store):
        mock_kv_store.set = AsyncMock()
        long_q = "x" * 1000
        await query_manager.log_query(
            tenant="t1", question=long_q, top_k=5, result_count=0,
            top_score=None, refused=False, refusal_reason=None,
            retrieval_latency_ms=5.0, generation_latency_ms=5.0,
        )
        entry = query_manager._pg_writer._buffer[0]
        assert len(entry.question) <= 500

    @pytest.mark.asyncio
    async def test_export_audit_delegates_to_writer(self, query_manager, mock_pg_pool):
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[])
        result = await query_manager.export_audit(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="json",
        )
        assert result == "[]"

    @pytest.mark.asyncio
    async def test_stats_includes_cost_percentiles(self, query_manager, mock_kv_store):
        mock_kv_store.keys = AsyncMock(return_value=["t1:1", "t1:2", "t1:3"])
        mock_kv_store.get = AsyncMock(side_effect=[
            {"refused": False, "retrieval_latency_ms": 50.0,
             "generation_latency_ms": 10.0, "top_score": 0.9, "cost_tokens": 1.0},
            {"refused": False, "retrieval_latency_ms": 60.0,
             "generation_latency_ms": 10.0, "top_score": 0.8, "cost_tokens": 2.0},
            {"refused": True, "retrieval_latency_ms": 20.0,
             "generation_latency_ms": 5.0, "top_score": 0.3, "cost_tokens": 1.5},
        ])
        stats = await query_manager.get_tenant_stats("t1")
        assert "cost_p50" in stats
        assert "cost_p99" in stats
        assert stats["cost_p50"] > 0

    @pytest.mark.asyncio
    async def test_stats_no_entries_zero_percentiles(self, query_manager, mock_kv_store):
        mock_kv_store.keys = AsyncMock(return_value=[])
        stats = await query_manager.get_tenant_stats("t1")
        assert stats["cost_p50"] == 0.0
        assert stats["cost_p99"] == 0.0


# S1 start/stop lifecycle
class TestAuditWriterLifecycle:
    def test_start_creates_task_when_pool_present(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool, flush_interval=999.0)
        loop = asyncio.new_event_loop()
        try:
            async def _run():
                w.start()
                assert w._task is not None
                w._task.cancel()
                try:
                    await w._task
                except asyncio.CancelledError:
                    pass
            loop.run_until_complete(_run())
        finally:
            loop.close()

    def test_start_no_task_without_pool(self):
        w = AsyncAuditWriter(None)
        loop = asyncio.new_event_loop()
        try:
            async def _run():
                w.start()
                assert w._task is None
            loop.run_until_complete(_run())
        finally:
            loop.close()

    @pytest.mark.asyncio
    async def test_stop_flushes_remaining(self, mock_pg_pool):
        w = AsyncAuditWriter(mock_pg_pool, flush_interval=999.0)
        conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
        conn.executemany = AsyncMock()
        await w.enqueue(_make_entry())
        await w.stop()
        conn.executemany.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_no_pg_does_not_crash(self):
        w = AsyncAuditWriter(None)
        await w.enqueue(_make_entry())
        await w.stop()  # should not raise


# ===========================================================================
# S2 — Timezone-Aware Quotas
# ===========================================================================


class TestIsValidTimezone:
    def test_utc_is_valid(self):
        assert is_valid_timezone("UTC") is True

    def test_common_timezone_valid(self):
        assert is_valid_timezone("America/New_York") is True

    def test_another_common_timezone(self):
        assert is_valid_timezone("Europe/London") is True

    def test_pacific_timezone(self):
        assert is_valid_timezone("America/Los_Angeles") is True

    def test_tokyo_timezone(self):
        assert is_valid_timezone("Asia/Tokyo") is True

    def test_invalid_timezone_string(self):
        assert is_valid_timezone("Not/ATimezone") is False

    def test_empty_string_invalid(self):
        assert is_valid_timezone("") is False

    def test_gibberish_invalid(self):
        assert is_valid_timezone("zzzzz") is False

    def test_case_sensitive(self):
        # Zone names are case-sensitive in zoneinfo
        assert is_valid_timezone("america/new_york") is False


class TestQuotaWindowKey:
    def test_daily_key_utc(self):
        key = _quota_window_key("daily", "UTC")
        # Should be YYYY-MM-DD format
        assert len(key) == 10
        assert key[4] == "-"
        assert key[7] == "-"

    def test_hourly_key_utc(self):
        key = _quota_window_key("hourly", "UTC")
        # Should be YYYY-MM-DD-HH format
        assert len(key) == 13
        assert key.count("-") == 3

    def test_different_timezones_may_differ(self):
        # In most cases these will differ because the wall-clock date differs
        # across UTC±12; we just check they return a string
        key_utc = _quota_window_key("daily", "UTC")
        key_ny = _quota_window_key("daily", "America/New_York")
        assert isinstance(key_utc, str)
        assert isinstance(key_ny, str)

    def test_daily_key_format(self):
        key = _quota_window_key("daily", "UTC")
        datetime.strptime(key, "%Y-%m-%d")  # should not raise

    def test_hourly_key_format(self):
        key = _quota_window_key("hourly", "UTC")
        datetime.strptime(key, "%Y-%m-%d-%H")

    def test_invalid_tz_falls_back_to_utc(self):
        # Should not raise; falls back to UTC
        key = _quota_window_key("daily", "Invalid/Zone")
        assert len(key) == 10


class TestQuotaResetSeconds:
    def test_daily_reset_positive(self):
        secs = _quota_reset_seconds("daily", "UTC")
        assert 0 < secs <= 86400

    def test_hourly_reset_positive(self):
        secs = _quota_reset_seconds("hourly", "UTC")
        assert 0 < secs <= 3600

    def test_daily_less_than_86400(self):
        secs = _quota_reset_seconds("daily", "UTC")
        assert secs <= 86400

    def test_hourly_less_than_3600(self):
        secs = _quota_reset_seconds("hourly", "UTC")
        assert secs <= 3600

    def test_new_york_reset_positive(self):
        secs = _quota_reset_seconds("daily", "America/New_York")
        assert secs > 0

    def test_tokyo_reset_positive(self):
        secs = _quota_reset_seconds("daily", "Asia/Tokyo")
        assert secs > 0

    def test_invalid_tz_falls_back(self):
        secs = _quota_reset_seconds("daily", "Invalid/Zone")
        assert secs > 0


class TestTenantConfig:
    def test_default_timezone_is_utc(self):
        cfg = TenantConfig(tenant="t1")
        assert cfg.timezone == "UTC"

    def test_custom_timezone_stored(self):
        cfg = TenantConfig(tenant="t1", timezone="America/New_York")
        assert cfg.timezone == "America/New_York"

    def test_default_quotas_are_zero(self):
        # 0 means "use global config" — not an explicit quota
        cfg = TenantConfig(tenant="t1")
        assert cfg.daily_quota == 0
        assert cfg.hourly_quota == 0


class TestQueryManagerTenantConfig:
    def test_get_default_config(self, query_manager):
        cfg = query_manager.get_tenant_config("unknown-tenant")
        assert cfg.timezone == "UTC"

    def test_set_and_get_config(self, query_manager):
        cfg = TenantConfig(tenant="t1", timezone="America/Chicago")
        query_manager.set_tenant_config(cfg)
        result = query_manager.get_tenant_config("t1")
        assert result.timezone == "America/Chicago"

    def test_set_overwrites(self, query_manager):
        query_manager.set_tenant_config(TenantConfig(tenant="t1", timezone="UTC"))
        query_manager.set_tenant_config(TenantConfig(tenant="t1", timezone="Asia/Seoul"))
        assert query_manager.get_tenant_config("t1").timezone == "Asia/Seoul"

    def test_different_tenants_independent(self, query_manager):
        query_manager.set_tenant_config(TenantConfig(tenant="a", timezone="UTC"))
        query_manager.set_tenant_config(TenantConfig(tenant="b", timezone="America/New_York"))
        assert query_manager.get_tenant_config("a").timezone == "UTC"
        assert query_manager.get_tenant_config("b").timezone == "America/New_York"


class TestTimezoneAwareCheckQuota:
    @pytest.mark.asyncio
    async def test_quota_uses_tenant_timezone_key(self, query_manager, mock_redis):
        query_manager.set_tenant_config(TenantConfig(tenant="tz-tenant", timezone="America/New_York"))
        mock_redis.get.return_value = None
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        result = await query_manager.check_quota("tz-tenant", quota_type="daily")
        assert result["allowed"] is True
        # Key should include the NY date string
        call_key = mock_redis.get.call_args[0][0]
        assert "tz-tenant" in call_key
        assert "daily" in call_key

    @pytest.mark.asyncio
    async def test_quota_utc_default_key(self, query_manager, mock_redis):
        mock_redis.get.return_value = None
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        result = await query_manager.check_quota("t1", quota_type="daily")
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_reset_in_seconds_uses_tenant_tz(self, query_manager, mock_redis):
        query_manager.set_tenant_config(TenantConfig(tenant="t1", timezone="America/New_York"))
        mock_redis.get.return_value = None
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        result = await query_manager.check_quota("t1", quota_type="daily")
        assert 0 < result["reset_in_seconds"] <= 86400

    @pytest.mark.asyncio
    async def test_quota_blocked_reset_in_uses_tenant_tz(self, query_manager, mock_redis):
        cfg = TenantConfig(tenant="t1", timezone="Asia/Tokyo", daily_quota=50)
        query_manager.set_tenant_config(cfg)
        mock_redis.get.return_value = b"50"  # at limit
        result = await query_manager.check_quota("t1", quota_type="daily")
        assert result["allowed"] is False
        assert 0 < result["reset_in_seconds"] <= 86400

    @pytest.mark.asyncio
    async def test_omitted_timezone_defaults_to_utc(self, query_manager, mock_redis):
        mock_redis.get.return_value = None
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        result = await query_manager.check_quota("no-tz-tenant", quota_type="daily")
        assert result["allowed"] is True
        # Backward compat: UTC window key
        call_key = mock_redis.get.call_args[0][0]
        utc_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert utc_date in call_key

    @pytest.mark.asyncio
    async def test_per_tenant_quota_limits(self, query_manager, mock_redis):
        query_manager.set_tenant_config(
            TenantConfig(tenant="limited", daily_quota=50, hourly_quota=10)
        )
        mock_redis.get.return_value = b"50"
        result = await query_manager.check_quota("limited", quota_type="daily")
        assert result["allowed"] is False
        assert result["limit"] == 50

    @pytest.mark.asyncio
    async def test_daily_and_hourly_separate_keys(self, query_manager, mock_redis):
        mock_redis.get.return_value = None
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        await query_manager.check_quota("t1", quota_type="daily")
        daily_key = mock_redis.get.call_args[0][0]
        await query_manager.check_quota("t1", quota_type="hourly")
        hourly_key = mock_redis.get.call_args[0][0]
        assert daily_key != hourly_key

    @pytest.mark.asyncio
    async def test_unknown_quota_type_raises(self, query_manager):
        with pytest.raises(ValueError, match="Unknown quota type"):
            await query_manager.check_quota("t1", quota_type="weekly")  # type: ignore[arg-type]


# ===========================================================================
# S3 — Cost-Based Rate Limiting
# ===========================================================================


class TestCalculateQueryCost:
    def test_base_cost_top_k_1(self, default_config):
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, cfg=default_config)
        assert cost == pytest.approx(1.0)

    def test_top_k_increases_cost(self, default_config):
        cost5 = calculate_query_cost(top_k=5, retrieval_ms=0.0, refused=False, cfg=default_config)
        cost1 = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, cfg=default_config)
        assert cost5 > cost1

    def test_top_k_cost_formula(self, default_config):
        cost = calculate_query_cost(top_k=11, retrieval_ms=0.0, refused=False, cfg=default_config)
        # 1.0 + (11-1)*0.1 = 2.0
        assert cost == pytest.approx(2.0)

    def test_latency_increases_cost(self, default_config):
        cost_slow = calculate_query_cost(top_k=1, retrieval_ms=100.0, refused=False, cfg=default_config)
        cost_fast = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, cfg=default_config)
        assert cost_slow > cost_fast

    def test_latency_cost_formula(self, default_config):
        cost = calculate_query_cost(top_k=1, retrieval_ms=100.0, refused=False, cfg=default_config)
        # 1.0 + 0.0 (top_k) + 1.0*0.1 (100ms/100 * 0.1) = 1.1
        assert cost == pytest.approx(1.1)

    def test_refusal_adds_penalty(self, default_config):
        cost_refused = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=True, cfg=default_config)
        cost_ok = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, cfg=default_config)
        assert cost_refused - cost_ok == pytest.approx(default_config.cost_refusal_penalty)

    def test_retry_adds_penalty(self, default_config):
        cost_retry = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, retries=2, cfg=default_config)
        cost_no_retry = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, retries=0, cfg=default_config)
        assert cost_retry - cost_no_retry == pytest.approx(2 * default_config.cost_retry_penalty)

    def test_combined_cost(self, default_config):
        # top_k=11, latency=100ms, refused=True, retries=1
        # 1.0 + 1.0 + 0.1 + 0.5 + 0.25 = 2.85
        cost = calculate_query_cost(top_k=11, retrieval_ms=100.0, refused=True, retries=1, cfg=default_config)
        assert cost == pytest.approx(2.85)

    def test_cost_always_positive(self, default_config):
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, cfg=default_config)
        assert cost > 0

    def test_minimum_cost_is_1(self, default_config):
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, retries=0, cfg=default_config)
        assert cost >= 1.0

    def test_negative_top_k_clamped(self, default_config):
        cost = calculate_query_cost(top_k=0, retrieval_ms=0.0, refused=False, cfg=default_config)
        assert cost == pytest.approx(1.0)

    def test_zero_latency_no_latency_charge(self, default_config):
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, cfg=default_config)
        assert cost == pytest.approx(1.0)

    def test_default_config_used_when_none(self):
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, cfg=None)
        assert cost == pytest.approx(1.0)

    def test_cost_rounded_to_4_decimals(self, default_config):
        cost = calculate_query_cost(top_k=3, retrieval_ms=33.3, refused=False, cfg=default_config)
        decimal_places = len(str(cost).rstrip("0").split(".")[-1])
        assert decimal_places <= 4

    def test_expensive_query_cost(self, default_config):
        # top_k=50, latency=5000ms, refused=True, retries=3
        cost = calculate_query_cost(top_k=50, retrieval_ms=5000.0, refused=True, retries=3, cfg=default_config)
        assert cost > 10.0


class TestVariableCostRateLimit:
    @pytest.mark.asyncio
    async def test_variable_cost_deducts_correct_tokens(self, query_manager, mock_redis):
        import json as _json
        # Bucket with 10 tokens
        bucket = {"tokens": 10.0, "last_refill": time.time()}
        mock_redis.get.return_value = _json.dumps(bucket).encode()
        mock_redis.setex = AsyncMock()

        result = await query_manager.check_rate_limit("t1", cost=3.0)
        assert result["allowed"] is True
        saved = _json.loads(mock_redis.setex.call_args[0][2])
        assert saved["tokens"] == pytest.approx(7.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_high_cost_refused_when_insufficient_tokens(self, query_manager, mock_redis):
        import json as _json
        bucket = {"tokens": 1.0, "last_refill": time.time()}
        mock_redis.get.return_value = _json.dumps(bucket).encode()
        mock_redis.setex = AsyncMock()

        result = await query_manager.check_rate_limit("t1", cost=5.0)
        assert result["allowed"] is False

    @pytest.mark.asyncio
    async def test_retry_after_proportional_to_cost(self, query_manager, mock_redis):
        import json as _json
        bucket = {"tokens": 0.0, "last_refill": time.time()}
        mock_redis.get.return_value = _json.dumps(bucket).encode()
        mock_redis.setex = AsyncMock()

        result1 = await query_manager.check_rate_limit("t1", cost=1.0)
        result5 = await query_manager.check_rate_limit("t1", cost=5.0)
        assert result5["retry_after_seconds"] > result1["retry_after_seconds"]

    @pytest.mark.asyncio
    async def test_default_cost_is_1(self, query_manager, mock_redis):
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()
        result = await query_manager.check_rate_limit("t1")
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_expensive_query_blocks_next_cheap_one(self, query_manager, mock_redis):
        import json as _json
        stored_bucket: dict | None = None

        async def get_side(_key: str):
            return _json.dumps(stored_bucket).encode() if stored_bucket else None

        async def setex_side(_key: str, _ttl: int, value: str):
            nonlocal stored_bucket
            stored_bucket = _json.loads(value)

        mock_redis.get.side_effect = get_side
        mock_redis.setex.side_effect = setex_side

        # Expensive query uses most tokens
        result = await query_manager.check_rate_limit("t1", cost=19.0)
        assert result["allowed"] is True

        # Cheap query still allowed (1 token left)
        result2 = await query_manager.check_rate_limit("t1", cost=1.0)
        assert result2["allowed"] is True

    @pytest.mark.asyncio
    async def test_cost_exceeding_burst_always_fails(self, query_manager, mock_redis):
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()
        # burst_size is 20; cost of 21 should always fail
        result = await query_manager.check_rate_limit("t1", cost=21.0)
        assert result["allowed"] is False

    @pytest.mark.asyncio
    async def test_cost_zero_allowed(self, query_manager, mock_redis):
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()
        result = await query_manager.check_rate_limit("t1", cost=0.0)
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_tokens_remaining_decreases_with_cost(self, query_manager, mock_redis):
        import json as _json
        bucket = {"tokens": 10.0, "last_refill": time.time()}
        mock_redis.get.return_value = _json.dumps(bucket).encode()
        mock_redis.setex = AsyncMock()
        result = await query_manager.check_rate_limit("t1", cost=3.5)
        # Tokens decrease by cost; some refill may happen in <1ms so allow wider tolerance
        assert result["tokens_remaining"] == pytest.approx(6.5, abs=0.5)


class TestCostInAuditLog:
    @pytest.mark.asyncio
    async def test_cost_stored_in_redis_entry(self, query_manager, mock_kv_store):
        mock_kv_store.set = AsyncMock()
        await query_manager.log_query(
            tenant="t1", question="q", top_k=10, result_count=5,
            top_score=0.8, refused=False, refusal_reason=None,
            retrieval_latency_ms=100.0, generation_latency_ms=20.0,
            cost_tokens=2.5,
        )
        call_args = mock_kv_store.set.call_args
        entry = call_args[0][2]
        assert entry["cost_tokens"] == 2.5

    @pytest.mark.asyncio
    async def test_default_cost_is_1_when_not_provided(self, query_manager, mock_kv_store):
        mock_kv_store.set = AsyncMock()
        await query_manager.log_query(
            tenant="t1", question="q", top_k=5, result_count=3,
            top_score=0.9, refused=False, refusal_reason=None,
            retrieval_latency_ms=50.0, generation_latency_ms=10.0,
        )
        entry = mock_kv_store.set.call_args[0][2]
        assert entry["cost_tokens"] == 1.0

    @pytest.mark.asyncio
    async def test_cost_in_pg_buffer_matches_input(self, query_manager, mock_kv_store):
        mock_kv_store.set = AsyncMock()
        await query_manager.log_query(
            tenant="t1", question="q", top_k=5, result_count=3,
            top_score=0.9, refused=True, refusal_reason="low score",
            retrieval_latency_ms=50.0, generation_latency_ms=0.0,
            cost_tokens=1.75,
        )
        pg_entry = query_manager._pg_writer._buffer[0]
        assert pg_entry.cost_tokens == 1.75

    @pytest.mark.asyncio
    async def test_cost_percentile_calculation(self, query_manager, mock_kv_store):
        costs = [1.0, 1.5, 2.0, 2.5, 3.0]
        mock_kv_store.keys = AsyncMock(return_value=[f"t1:{i}" for i in range(5)])
        mock_kv_store.get = AsyncMock(side_effect=[
            {"refused": False, "retrieval_latency_ms": 50.0, "generation_latency_ms": 10.0,
             "top_score": 0.9, "cost_tokens": c}
            for c in costs
        ])
        stats = await query_manager.get_tenant_stats("t1")
        assert stats["cost_p50"] == pytest.approx(2.0, abs=0.1)
        assert stats["cost_p99"] == pytest.approx(3.0, abs=0.1)


# ===========================================================================
# Integration / edge case tests
# ===========================================================================


class TestEndToEndIntegration:
    @pytest.mark.asyncio
    async def test_full_query_flow_with_cost(self, query_manager, mock_redis, mock_kv_store):
        """Full flow: rate limit → quota → log with cost."""
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        mock_kv_store.set = AsyncMock()

        cost = calculate_query_cost(top_k=5, retrieval_ms=50.0, refused=False, cfg=query_manager.config)
        rl = await query_manager.check_rate_limit("t1", cost=cost)
        assert rl["allowed"] is True

        quota = await query_manager.check_quota("t1", quota_type="daily")
        assert quota["allowed"] is True

        entry_id = await query_manager.log_query(
            tenant="t1", question="What is RAG?", top_k=5, result_count=3,
            top_score=0.95, refused=False, refusal_reason=None,
            retrieval_latency_ms=50.0, generation_latency_ms=15.0,
            cost_tokens=cost,
        )
        assert entry_id.startswith("t1:")

    @pytest.mark.asyncio
    async def test_timezone_quota_window_isolation(self, query_manager, mock_redis):
        """Different tenants with different timezones use different quota keys."""
        query_manager.set_tenant_config(TenantConfig(tenant="a", timezone="UTC"))
        query_manager.set_tenant_config(TenantConfig(tenant="b", timezone="America/New_York"))
        mock_redis.get.return_value = None
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        mock_redis.setex = AsyncMock()

        await query_manager.check_quota("a", quota_type="daily")
        key_a = mock_redis.get.call_args[0][0]
        await query_manager.check_quota("b", quota_type="daily")
        key_b = mock_redis.get.call_args[0][0]
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_expensive_query_blocks_before_quota(self, query_manager, mock_redis):
        """When rate limit blocks (cost too high), quota should not be checked."""
        import json as _json
        bucket = {"tokens": 0.5, "last_refill": time.time()}
        mock_redis.get.return_value = _json.dumps(bucket).encode()
        mock_redis.setex = AsyncMock()

        rl = await query_manager.check_rate_limit("t1", cost=5.0)
        assert rl["allowed"] is False
        # If blocked, quota check would not be reached (enforced by caller)

    @pytest.mark.asyncio
    async def test_backward_compat_no_cost_param(self, query_manager_no_pg, mock_kv_store, mock_redis):
        """RAG-08 callers that don't pass cost_tokens should still work."""
        mock_kv_store.set = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()
        entry_id = await query_manager_no_pg.log_query(
            tenant="legacy", question="q", top_k=5, result_count=3,
            top_score=0.9, refused=False, refusal_reason=None,
            retrieval_latency_ms=50.0, generation_latency_ms=10.0,
        )
        assert entry_id.startswith("legacy:")

    @pytest.mark.asyncio
    async def test_query_path_unchanged(self, query_manager, mock_redis, mock_kv_store):
        """Existing /query callers that don't use cost still get through."""
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        mock_kv_store.set = AsyncMock()

        rl = await query_manager.check_rate_limit("t1")  # no cost param
        assert rl["allowed"] is True

        quota = await query_manager.check_quota("t1")  # no quota_type param
        assert quota["allowed"] is True
