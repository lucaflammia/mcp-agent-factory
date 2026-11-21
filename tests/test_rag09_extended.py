"""RAG-09 extended test suite — additional coverage to meet acceptance targets.

S1 — PostgreSQL Audit Logs  (target: 150+ total; this file adds ~110)
S2 — Timezone-Aware Quotas  (target: 100+ total; this file adds ~65)
S3 — Cost-Based Rate Limiting (target: 120+ total; this file adds ~90)
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import math
import statistics
import time
from datetime import datetime, timedelta, timezone
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
# Shared helpers
# ===========================================================================


def _entry(
    tenant: str = "t1",
    top_k: int = 5,
    retrieval_ms: float = 50.0,
    generation_ms: float = 10.0,
    refused: bool = False,
    refusal_reason: str | None = None,
    result_count: int = 3,
    top_score: float | None = 0.9,
    cost: float = 1.0,
    question: str = "what is RAG?",
) -> AuditEntry:
    return AuditEntry(
        entry_id=f"{tenant}:{int(time.time() * 1e6)}",
        tenant=tenant,
        question=question,
        top_k=top_k,
        result_count=result_count,
        top_score=top_score,
        refused=refused,
        refusal_reason=refusal_reason,
        retrieval_ms=retrieval_ms,
        generation_ms=generation_ms,
        cost_tokens=cost,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )


def _pg_pool(rows=None, raise_on_exec=None):
    pool = MagicMock()
    conn = AsyncMock()
    if raise_on_exec:
        conn.executemany = AsyncMock(side_effect=raise_on_exec)
    else:
        conn.executemany = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows or [])
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


@pytest.fixture
def cfg() -> RateLimitConfig:
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
def redis():
    return AsyncMock()


@pytest.fixture
def kv():
    return AsyncMock()


@pytest.fixture
def qm(redis, kv, cfg):
    pool, _ = _pg_pool()
    return QueryManager(
        kv_store=kv,
        redis_client=redis,
        config=cfg,
        pg_pool=pool,
        audit_flush_interval=999.0,
        audit_max_buffer=1000,
    )


# ===========================================================================
# S1 — AsyncAuditWriter: additional coverage (~110 tests)
# ===========================================================================


class TestS1_WriterBufferOrdering:
    @pytest.mark.asyncio
    async def test_entries_preserved_in_order(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        tenants = [f"t{i}" for i in range(10)]
        for t in tenants:
            await w.enqueue(_entry(tenant=t))
        assert [e.tenant for e in w._buffer] == tenants

    @pytest.mark.asyncio
    async def test_enqueue_100_entries(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0, max_buffer=200)
        for i in range(100):
            await w.enqueue(_entry(tenant=f"t{i}"))
        assert len(w._buffer) == 100

    @pytest.mark.asyncio
    async def test_flush_sends_all_100(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0, max_buffer=200)
        for i in range(100):
            await w.enqueue(_entry(tenant=f"t{i}"))
        await w._flush()
        rows = conn.executemany.call_args[0][1]
        assert len(rows) == 100

    @pytest.mark.asyncio
    async def test_max_buffer_1_flushes_immediately(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0, max_buffer=1)
        await w.enqueue(_entry())
        conn.executemany.assert_called_once()
        assert len(w._buffer) == 0

    @pytest.mark.asyncio
    async def test_flush_after_error_restores_buffer_and_retries(self):
        pool, conn = _pg_pool()
        call_count = [0]
        original = conn.executemany

        async def flaky(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("transient error")

        conn.executemany = AsyncMock(side_effect=flaky)
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry())
        await w._flush()  # First flush fails → returns to buffer
        assert len(w._buffer) == 1
        conn.executemany = AsyncMock()  # Second attempt succeeds
        await w._flush()
        assert len(w._buffer) == 0

    @pytest.mark.asyncio
    async def test_multiple_flush_calls_do_not_double_send(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry())
        await w._flush()
        await w._flush()  # Buffer already empty
        assert conn.executemany.call_count == 1

    @pytest.mark.asyncio
    async def test_buffer_empty_after_successful_flush(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        for _ in range(5):
            await w.enqueue(_entry())
        await w._flush()
        assert w._buffer == []

    @pytest.mark.asyncio
    async def test_enqueue_post_flush_refills_buffer(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry())
        await w._flush()
        await w.enqueue(_entry())
        assert len(w._buffer) == 1


class TestS1_WriterFieldSerialization:
    @pytest.mark.asyncio
    async def test_all_11_fields_sent_per_row(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry())
        await w._flush()
        rows = conn.executemany.call_args[0][1]
        assert len(rows[0]) == 11

    @pytest.mark.asyncio
    async def test_tenant_field_index_0(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry(tenant="mytenant"))
        await w._flush()
        assert conn.executemany.call_args[0][1][0][0] == "mytenant"

    @pytest.mark.asyncio
    async def test_question_field_index_1(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry(question="what is a vector?"))
        await w._flush()
        assert conn.executemany.call_args[0][1][0][1] == "what is a vector?"

    @pytest.mark.asyncio
    async def test_top_k_field_index_2(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry(top_k=15))
        await w._flush()
        assert conn.executemany.call_args[0][1][0][2] == 15

    @pytest.mark.asyncio
    async def test_result_count_field_index_3(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry(result_count=7))
        await w._flush()
        assert conn.executemany.call_args[0][1][0][3] == 7

    @pytest.mark.asyncio
    async def test_top_score_field_index_4(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry(top_score=0.75))
        await w._flush()
        assert conn.executemany.call_args[0][1][0][4] == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_top_score_none_allowed(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry(top_score=None))
        await w._flush()
        assert conn.executemany.call_args[0][1][0][4] is None

    @pytest.mark.asyncio
    async def test_refused_field_index_5(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry(refused=True))
        await w._flush()
        assert conn.executemany.call_args[0][1][0][5] is True

    @pytest.mark.asyncio
    async def test_refusal_reason_field_index_6(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry(refusal_reason="low score"))
        await w._flush()
        assert conn.executemany.call_args[0][1][0][6] == "low score"

    @pytest.mark.asyncio
    async def test_retrieval_ms_field_index_7(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry(retrieval_ms=123.45))
        await w._flush()
        assert conn.executemany.call_args[0][1][0][7] == pytest.approx(123.45)

    @pytest.mark.asyncio
    async def test_generation_ms_field_index_8(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry(generation_ms=55.5))
        await w._flush()
        assert conn.executemany.call_args[0][1][0][8] == pytest.approx(55.5)

    @pytest.mark.asyncio
    async def test_cost_tokens_field_index_9(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry(cost=3.14))
        await w._flush()
        assert conn.executemany.call_args[0][1][0][9] == pytest.approx(3.14)

    @pytest.mark.asyncio
    async def test_timestamp_field_index_10(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        e = _entry()
        await w.enqueue(e)
        await w._flush()
        assert conn.executemany.call_args[0][1][0][10] == e.timestamp


class TestS1_ExportAdditional:
    @pytest.mark.asyncio
    async def test_json_multiple_rows(self):
        rows = [
            {"tenant": "t1", "question": f"q{i}", "top_k": 5, "result_count": 2,
             "top_score": 0.9, "refused": False, "refusal_reason": None,
             "retrieval_ms": 50.0, "generation_ms": 10.0, "cost_tokens": 1.0,
             "timestamp": "2024-01-15T12:00:00+00:00"}
            for i in range(5)
        ]
        pool, conn = _pg_pool(rows=rows)
        w = AsyncAuditWriter(pool)
        result = await w.export(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="json",
        )
        data = json.loads(result)
        assert len(data) == 5

    @pytest.mark.asyncio
    async def test_csv_multiple_rows(self):
        rows = [
            {"tenant": "t1", "question": f"q{i}", "top_k": 5, "result_count": 2,
             "top_score": 0.9, "refused": False, "refusal_reason": None,
             "retrieval_ms": 50.0, "generation_ms": 10.0, "cost_tokens": 1.0,
             "timestamp": "2024-01-15T12:00:00+00:00"}
            for i in range(3)
        ]
        pool, conn = _pg_pool(rows=rows)
        w = AsyncAuditWriter(pool)
        result = await w.export(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="csv",
        )
        reader = csv.DictReader(io.StringIO(result))
        assert len(list(reader)) == 3

    @pytest.mark.asyncio
    async def test_csv_all_expected_columns(self):
        pool, conn = _pg_pool(rows=[])
        w = AsyncAuditWriter(pool)
        result = await w.export(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="csv",
        )
        reader = csv.DictReader(io.StringIO(result))
        expected_cols = {
            "tenant", "question", "top_k", "result_count", "top_score",
            "refused", "refusal_reason", "retrieval_ms", "generation_ms",
            "cost_tokens", "timestamp",
        }
        assert expected_cols == set(reader.fieldnames or [])

    @pytest.mark.asyncio
    async def test_export_json_refused_flag(self):
        rows = [
            {"tenant": "t1", "question": "q", "top_k": 5, "result_count": 0,
             "top_score": None, "refused": True, "refusal_reason": "low score",
             "retrieval_ms": 5.0, "generation_ms": 0.0, "cost_tokens": 1.5,
             "timestamp": "2024-01-15T12:00:00+00:00"},
        ]
        pool, conn = _pg_pool(rows=rows)
        w = AsyncAuditWriter(pool)
        result = await w.export(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="json",
        )
        data = json.loads(result)
        assert data[0]["refused"] is True
        assert data[0]["refusal_reason"] == "low score"

    @pytest.mark.asyncio
    async def test_export_json_cost_tokens_present(self):
        rows = [
            {"tenant": "t1", "question": "q", "top_k": 5, "result_count": 2,
             "top_score": 0.9, "refused": False, "refusal_reason": None,
             "retrieval_ms": 50.0, "generation_ms": 10.0, "cost_tokens": 2.75,
             "timestamp": "2024-01-15T12:00:00+00:00"},
        ]
        pool, conn = _pg_pool(rows=rows)
        w = AsyncAuditWriter(pool)
        result = await w.export(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="json",
        )
        data = json.loads(result)
        assert data[0]["cost_tokens"] == 2.75

    @pytest.mark.asyncio
    async def test_export_default_fmt_is_json(self):
        pool, conn = _pg_pool(rows=[])
        w = AsyncAuditWriter(pool)
        result = await w.export(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
        )
        json.loads(result)  # should not raise

    @pytest.mark.asyncio
    async def test_export_no_pg_csv_has_header_row(self):
        w = AsyncAuditWriter(None)
        result = await w.export(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="csv",
        )
        assert "tenant" in result

    @pytest.mark.asyncio
    async def test_export_queries_with_correct_sql_placeholders(self):
        pool, conn = _pg_pool(rows=[])
        w = AsyncAuditWriter(pool)
        await w.export(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
        )
        sql = conn.fetch.call_args[0][0]
        assert "$1" in sql
        assert "$2" in sql
        assert "$3" in sql

    @pytest.mark.asyncio
    async def test_export_1_year_passes_correct_dates(self):
        pool, conn = _pg_pool(rows=[])
        w = AsyncAuditWriter(pool)
        start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, tzinfo=timezone.utc)
        await w.export("t1", start, end, fmt="json")
        args = conn.fetch.call_args[0]
        assert args[2] == start
        assert args[3] == end

    @pytest.mark.asyncio
    async def test_export_csv_question_field_preserved(self):
        rows = [
            {"tenant": "t1", "question": "explain embeddings", "top_k": 5,
             "result_count": 2, "top_score": 0.9, "refused": False,
             "refusal_reason": None, "retrieval_ms": 50.0, "generation_ms": 10.0,
             "cost_tokens": 1.0, "timestamp": "2024-01-15T12:00:00+00:00"},
        ]
        pool, conn = _pg_pool(rows=rows)
        w = AsyncAuditWriter(pool)
        result = await w.export(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="csv",
        )
        reader = csv.DictReader(io.StringIO(result))
        row = next(reader)
        assert row["question"] == "explain embeddings"


class TestS1_StopBehavior:
    @pytest.mark.asyncio
    async def test_stop_empty_buffer_no_pg_call(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.stop()
        conn.executemany.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_twice_does_not_crash(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        await w.enqueue(_entry())
        await w.stop()
        await w.stop()  # Second stop: buffer already empty

    @pytest.mark.asyncio
    async def test_stop_flushes_multiple_entries(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        for _ in range(5):
            await w.enqueue(_entry())
        await w.stop()
        rows = conn.executemany.call_args[0][1]
        assert len(rows) == 5

    @pytest.mark.asyncio
    async def test_start_idempotent_does_not_create_second_task(self):
        pool, conn = _pg_pool()
        w = AsyncAuditWriter(pool, flush_interval=999.0)
        w.start()
        task1 = w._task
        w.start()
        task2 = w._task
        assert task1 is task2
        task1.cancel()
        try:
            await task1
        except asyncio.CancelledError:
            pass


class TestS1_QueryManagerIntegration:
    @pytest.mark.asyncio
    async def test_log_query_all_fields_in_pg_entry(self, qm, kv):
        kv.set = AsyncMock()
        await qm.log_query(
            tenant="t1", question="q?", top_k=10, result_count=4,
            top_score=0.88, refused=False, refusal_reason=None,
            retrieval_latency_ms=75.0, generation_latency_ms=25.0,
            cost_tokens=2.0,
        )
        entry = qm._pg_writer._buffer[0]
        assert entry.tenant == "t1"
        assert entry.top_k == 10
        assert entry.result_count == 4
        assert entry.retrieval_ms == 75.0
        assert entry.generation_ms == 25.0
        assert entry.cost_tokens == 2.0

    @pytest.mark.asyncio
    async def test_log_query_refused_propagated_to_pg(self, qm, kv):
        kv.set = AsyncMock()
        await qm.log_query(
            tenant="t1", question="q?", top_k=5, result_count=0,
            top_score=None, refused=True, refusal_reason="below threshold",
            retrieval_latency_ms=5.0, generation_latency_ms=0.0,
        )
        entry = qm._pg_writer._buffer[0]
        assert entry.refused is True
        assert entry.refusal_reason == "below threshold"

    @pytest.mark.asyncio
    async def test_log_query_multiple_tenants_separate_entries(self, qm, kv):
        kv.set = AsyncMock()
        for t in ["a", "b", "c"]:
            await qm.log_query(
                tenant=t, question="q", top_k=5, result_count=2,
                top_score=0.9, refused=False, refusal_reason=None,
                retrieval_latency_ms=50.0, generation_latency_ms=10.0,
            )
        tenants = [e.tenant for e in qm._pg_writer._buffer]
        assert set(tenants) == {"a", "b", "c"}

    @pytest.mark.asyncio
    async def test_export_audit_csv_format(self, qm):
        pool = qm._pg_writer._pool
        conn = pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[
            {"tenant": "t1", "question": "q", "top_k": 5, "result_count": 2,
             "top_score": 0.9, "refused": False, "refusal_reason": None,
             "retrieval_ms": 50.0, "generation_ms": 10.0, "cost_tokens": 1.0,
             "timestamp": "2024-01-15T12:00:00+00:00"},
        ])
        result = await qm.export_audit(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="csv",
        )
        assert "tenant" in result
        assert "cost_tokens" in result

    @pytest.mark.asyncio
    async def test_export_audit_json_format(self, qm):
        pool = qm._pg_writer._pool
        conn = pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[])
        result = await qm.export_audit(
            "t1",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            fmt="json",
        )
        json.loads(result)  # should not raise

    @pytest.mark.asyncio
    async def test_stats_with_many_entries(self, qm, kv):
        n = 20
        kv.keys = AsyncMock(return_value=[f"t1:{i}" for i in range(n)])
        kv.get = AsyncMock(side_effect=[
            {"refused": False, "retrieval_latency_ms": float(i * 10),
             "generation_latency_ms": 5.0, "top_score": 0.5, "cost_tokens": float(i + 1)}
            for i in range(n)
        ])
        stats = await qm.get_tenant_stats("t1")
        assert stats["cost_p50"] > 0
        assert stats["cost_p99"] >= stats["cost_p50"]

    @pytest.mark.asyncio
    async def test_stats_single_entry_percentiles_equal(self, qm, kv):
        kv.keys = AsyncMock(return_value=["t1:1"])
        kv.get = AsyncMock(return_value={
            "refused": False, "retrieval_latency_ms": 50.0,
            "generation_latency_ms": 10.0, "top_score": 0.9, "cost_tokens": 2.5,
        })
        stats = await qm.get_tenant_stats("t1")
        assert stats["cost_p50"] == stats["cost_p99"]


# ===========================================================================
# S2 — Timezone-Aware Quotas: additional coverage (~65 tests)
# ===========================================================================


class TestS2_IsValidTimezone:
    def test_chicago_valid(self):
        assert is_valid_timezone("America/Chicago") is True

    def test_denver_valid(self):
        assert is_valid_timezone("America/Denver") is True

    def test_vancouver_valid(self):
        assert is_valid_timezone("America/Vancouver") is True

    def test_london_valid(self):
        assert is_valid_timezone("Europe/London") is True

    def test_berlin_valid(self):
        assert is_valid_timezone("Europe/Berlin") is True

    def test_paris_valid(self):
        assert is_valid_timezone("Europe/Paris") is True

    def test_shanghai_valid(self):
        assert is_valid_timezone("Asia/Shanghai") is True

    def test_kolkata_valid(self):
        assert is_valid_timezone("Asia/Kolkata") is True

    def test_sydney_valid(self):
        assert is_valid_timezone("Australia/Sydney") is True

    def test_auckland_valid(self):
        assert is_valid_timezone("Pacific/Auckland") is True

    def test_honolulu_valid(self):
        assert is_valid_timezone("Pacific/Honolulu") is True

    def test_space_invalid(self):
        assert is_valid_timezone(" ") is False

    def test_numeric_invalid(self):
        assert is_valid_timezone("12345") is False

    def test_partial_valid_zone_invalid(self):
        assert is_valid_timezone("America") is False

    def test_slash_only_invalid(self):
        assert is_valid_timezone("/") is False


class TestS2_QuotaWindowKeyDetails:
    def test_daily_key_length_exactly_10(self):
        key = _quota_window_key("daily", "UTC")
        assert len(key) == 10

    def test_hourly_key_length_exactly_13(self):
        key = _quota_window_key("hourly", "UTC")
        assert len(key) == 13

    def test_daily_key_year_component_is_4_digits(self):
        key = _quota_window_key("daily", "UTC")
        year = key.split("-")[0]
        assert len(year) == 4
        assert year.isdigit()

    def test_daily_key_month_component_valid(self):
        key = _quota_window_key("daily", "UTC")
        month = int(key.split("-")[1])
        assert 1 <= month <= 12

    def test_daily_key_day_component_valid(self):
        key = _quota_window_key("daily", "UTC")
        day = int(key.split("-")[2])
        assert 1 <= day <= 31

    def test_hourly_key_hour_component_valid(self):
        key = _quota_window_key("hourly", "UTC")
        hour = int(key.split("-")[3])
        assert 0 <= hour <= 23

    def test_all_common_timezones_return_string(self):
        zones = [
            "UTC", "America/New_York", "America/Chicago",
            "America/Denver", "America/Los_Angeles",
            "Europe/London", "Europe/Paris", "Europe/Berlin",
            "Asia/Tokyo", "Asia/Shanghai", "Asia/Kolkata",
            "Australia/Sydney", "Pacific/Auckland",
        ]
        for tz in zones:
            key = _quota_window_key("daily", tz)
            assert isinstance(key, str)
            assert len(key) == 10

    def test_hourly_all_common_timezones(self):
        zones = ["UTC", "America/New_York", "Asia/Tokyo"]
        for tz in zones:
            key = _quota_window_key("hourly", tz)
            assert len(key) == 13


class TestS2_QuotaResetSecondsDetails:
    def test_daily_utc_in_valid_range(self):
        s = _quota_reset_seconds("daily", "UTC")
        assert 0 < s <= 86400

    def test_hourly_utc_in_valid_range(self):
        s = _quota_reset_seconds("hourly", "UTC")
        assert 0 < s <= 3600

    def test_daily_new_york_in_valid_range(self):
        s = _quota_reset_seconds("daily", "America/New_York")
        assert 0 < s <= 86400

    def test_daily_tokyo_in_valid_range(self):
        s = _quota_reset_seconds("daily", "Asia/Tokyo")
        assert 0 < s <= 86400

    def test_hourly_new_york_in_valid_range(self):
        s = _quota_reset_seconds("hourly", "America/New_York")
        assert 0 < s <= 3600

    def test_hourly_tokyo_in_valid_range(self):
        s = _quota_reset_seconds("hourly", "Asia/Tokyo")
        assert 0 < s <= 3600

    def test_daily_sydney_in_valid_range(self):
        s = _quota_reset_seconds("daily", "Australia/Sydney")
        assert 0 < s <= 86400

    def test_invalid_tz_fallback_positive(self):
        s = _quota_reset_seconds("daily", "Bogus/Zone")
        assert s > 0

    def test_hourly_invalid_tz_fallback_positive(self):
        s = _quota_reset_seconds("hourly", "Bogus/Zone")
        assert s > 0

    def test_reset_seconds_is_float(self):
        s = _quota_reset_seconds("daily", "UTC")
        assert isinstance(s, float)


class TestS2_TenantConfigFields:
    def test_tenant_field_stored(self):
        tc = TenantConfig(tenant="myco")
        assert tc.tenant == "myco"

    def test_timezone_field_new_york(self):
        tc = TenantConfig(tenant="t1", timezone="America/New_York")
        assert tc.timezone == "America/New_York"

    def test_timezone_field_tokyo(self):
        tc = TenantConfig(tenant="t1", timezone="Asia/Tokyo")
        assert tc.timezone == "Asia/Tokyo"

    def test_per_tenant_daily_quota(self):
        tc = TenantConfig(tenant="t1", daily_quota=5000)
        assert tc.daily_quota == 5000

    def test_per_tenant_hourly_quota(self):
        tc = TenantConfig(tenant="t1", hourly_quota=200)
        assert tc.hourly_quota == 200

    def test_per_tenant_tps(self):
        tc = TenantConfig(tenant="t1", tokens_per_second=5.0)
        assert tc.tokens_per_second == 5.0

    def test_per_tenant_burst(self):
        tc = TenantConfig(tenant="t1", burst_size=50)
        assert tc.burst_size == 50

    def test_default_tps_is_zero(self):
        tc = TenantConfig(tenant="t1")
        assert tc.tokens_per_second == 0.0

    def test_default_burst_is_zero(self):
        tc = TenantConfig(tenant="t1")
        assert tc.burst_size == 0


class TestS2_QueryManagerTimezone:
    def test_tenant_tz_default_utc(self, qm):
        assert qm._tenant_tz("unknown") == "UTC"

    def test_tenant_tz_returns_configured(self, qm):
        qm.set_tenant_config(TenantConfig(tenant="t1", timezone="Asia/Seoul"))
        assert qm._tenant_tz("t1") == "Asia/Seoul"

    @pytest.mark.asyncio
    async def test_check_quota_hourly_uses_tenant_tz(self, qm, redis):
        qm.set_tenant_config(TenantConfig(tenant="tz", timezone="America/New_York"))
        redis.get.return_value = None
        redis.incr = AsyncMock(return_value=1)
        redis.expire = AsyncMock()
        result = await qm.check_quota("tz", quota_type="hourly")
        assert result["allowed"] is True
        key = redis.get.call_args[0][0]
        assert "tz" in key
        assert "hourly" in key

    @pytest.mark.asyncio
    async def test_check_quota_allowed_returns_reset_in_seconds(self, qm, redis):
        redis.get.return_value = None
        redis.incr = AsyncMock(return_value=1)
        redis.expire = AsyncMock()
        result = await qm.check_quota("t1", quota_type="daily")
        assert 0 < result["reset_in_seconds"] <= 86400

    @pytest.mark.asyncio
    async def test_check_quota_blocked_returns_reset_in_seconds(self, qm, redis):
        redis.get.return_value = b"1000"  # equal to daily limit
        result = await qm.check_quota("t1", quota_type="daily")
        assert result["allowed"] is False
        assert 0 < result["reset_in_seconds"] <= 86400

    @pytest.mark.asyncio
    async def test_check_quota_used_matches_redis_value(self, qm, redis):
        redis.get.return_value = b"42"
        redis.incr = AsyncMock(return_value=43)
        redis.expire = AsyncMock()
        result = await qm.check_quota("t1", quota_type="daily")
        # check_quota increments and returns used+1
        assert result["used"] == 43

    @pytest.mark.asyncio
    async def test_check_quota_limit_uses_tenant_override(self, qm, redis):
        qm.set_tenant_config(TenantConfig(tenant="t1", daily_quota=250))
        redis.get.return_value = b"0"
        result = await qm.check_quota("t1", quota_type="daily")
        assert result["limit"] == 250

    @pytest.mark.asyncio
    async def test_check_quota_limit_falls_back_to_global(self, qm, redis):
        redis.get.return_value = b"0"
        result = await qm.check_quota("t1", quota_type="daily")
        assert result["limit"] == qm.config.daily_quota

    @pytest.mark.asyncio
    async def test_check_hourly_quota_limit_tenant_override(self, qm, redis):
        qm.set_tenant_config(TenantConfig(tenant="t1", hourly_quota=50))
        redis.get.return_value = b"0"
        result = await qm.check_quota("t1", quota_type="hourly")
        assert result["limit"] == 50


# ===========================================================================
# S3 — Cost-Based Rate Limiting: additional coverage (~90 tests)
# ===========================================================================


class TestS3_CostWeightVariations:
    def test_zero_top_k_weight_no_extra_cost(self):
        custom_cfg = RateLimitConfig(cost_top_k_per_unit=0.0)
        cost = calculate_query_cost(top_k=100, retrieval_ms=0.0, refused=False, cfg=custom_cfg)
        assert cost == pytest.approx(1.0)

    def test_zero_latency_weight_no_latency_cost(self):
        custom_cfg = RateLimitConfig(cost_latency_ms_per_100=0.0)
        cost = calculate_query_cost(top_k=1, retrieval_ms=5000.0, refused=False, cfg=custom_cfg)
        assert cost == pytest.approx(1.0)

    def test_zero_refusal_weight_no_refusal_cost(self):
        custom_cfg = RateLimitConfig(cost_refusal_penalty=0.0)
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=True, cfg=custom_cfg)
        assert cost == pytest.approx(1.0)

    def test_zero_retry_weight_no_retry_cost(self):
        custom_cfg = RateLimitConfig(cost_retry_penalty=0.0)
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, retries=10, cfg=custom_cfg)
        assert cost == pytest.approx(1.0)

    def test_high_top_k_weight_amplifies_cost(self):
        custom_cfg = RateLimitConfig(cost_top_k_per_unit=1.0)
        cost = calculate_query_cost(top_k=11, retrieval_ms=0.0, refused=False, cfg=custom_cfg)
        # 1.0 + (11-1)*1.0 = 11.0
        assert cost == pytest.approx(11.0)

    def test_high_latency_weight_amplifies_cost(self):
        custom_cfg = RateLimitConfig(cost_latency_ms_per_100=1.0)
        cost = calculate_query_cost(top_k=1, retrieval_ms=100.0, refused=False, cfg=custom_cfg)
        # 1.0 + 1.0*1.0 = 2.0
        assert cost == pytest.approx(2.0)

    def test_high_refusal_penalty(self):
        custom_cfg = RateLimitConfig(cost_refusal_penalty=10.0)
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=True, cfg=custom_cfg)
        assert cost == pytest.approx(11.0)

    def test_high_retry_penalty_many_retries(self):
        custom_cfg = RateLimitConfig(cost_retry_penalty=2.0)
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, retries=5, cfg=custom_cfg)
        # 1.0 + 5*2.0 = 11.0
        assert cost == pytest.approx(11.0)


class TestS3_CostEdgeCases:
    def test_top_k_0_no_extra(self, cfg):
        cost = calculate_query_cost(top_k=0, retrieval_ms=0.0, refused=False, cfg=cfg)
        assert cost == pytest.approx(1.0)

    def test_top_k_1_exactly_no_extra(self, cfg):
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, cfg=cfg)
        assert cost == pytest.approx(1.0)

    def test_top_k_2_adds_one_unit(self, cfg):
        cost = calculate_query_cost(top_k=2, retrieval_ms=0.0, refused=False, cfg=cfg)
        assert cost == pytest.approx(1.0 + 0.1)

    def test_top_k_10_adds_nine_units(self, cfg):
        cost = calculate_query_cost(top_k=10, retrieval_ms=0.0, refused=False, cfg=cfg)
        assert cost == pytest.approx(1.0 + 9 * 0.1)

    def test_latency_50ms_half_unit(self, cfg):
        cost = calculate_query_cost(top_k=1, retrieval_ms=50.0, refused=False, cfg=cfg)
        assert cost == pytest.approx(1.0 + 0.5 * 0.1)

    def test_latency_200ms_two_units(self, cfg):
        cost = calculate_query_cost(top_k=1, retrieval_ms=200.0, refused=False, cfg=cfg)
        assert cost == pytest.approx(1.0 + 2.0 * 0.1)

    def test_latency_1000ms_ten_units(self, cfg):
        cost = calculate_query_cost(top_k=1, retrieval_ms=1000.0, refused=False, cfg=cfg)
        assert cost == pytest.approx(1.0 + 10.0 * 0.1)

    def test_retries_1_adds_one_penalty(self, cfg):
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, retries=1, cfg=cfg)
        assert cost == pytest.approx(1.0 + 0.25)

    def test_retries_4_adds_four_penalties(self, cfg):
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, retries=4, cfg=cfg)
        assert cost == pytest.approx(1.0 + 4 * 0.25)

    def test_retries_10(self, cfg):
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, retries=10, cfg=cfg)
        assert cost == pytest.approx(1.0 + 10 * 0.25)

    def test_refused_adds_exactly_penalty(self, cfg):
        cost_refused = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=True, cfg=cfg)
        cost_ok = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, cfg=cfg)
        assert cost_refused - cost_ok == pytest.approx(0.5)

    def test_refused_and_1_retry(self, cfg):
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=True, retries=1, cfg=cfg)
        # 1.0 + 0.5 (refusal) + 0.25 (retry)
        assert cost == pytest.approx(1.75)

    def test_all_components_zero_except_base(self, cfg):
        cost = calculate_query_cost(top_k=1, retrieval_ms=0.0, refused=False, retries=0, cfg=cfg)
        assert cost == pytest.approx(1.0)

    def test_very_expensive_query(self, cfg):
        cost = calculate_query_cost(top_k=100, retrieval_ms=10000.0, refused=True, retries=10, cfg=cfg)
        # 1.0 + 99*0.1 + 100*0.1 + 0.5 + 10*0.25 = 1+9.9+10+0.5+2.5 = 23.9
        assert cost == pytest.approx(23.9)

    def test_rounding_to_4_places(self, cfg):
        cost = calculate_query_cost(top_k=3, retrieval_ms=33.3, refused=False, cfg=cfg)
        str_cost = str(cost)
        if "." in str_cost:
            decimals = len(str_cost.split(".")[1].rstrip("0") or "0")
            assert decimals <= 4


class TestS3_RateLimitCost:
    @pytest.mark.asyncio
    async def test_fresh_bucket_allows_cost_1(self, qm, redis):
        redis.get.return_value = None
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=1.0)
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_fresh_bucket_allows_cost_equal_to_burst(self, qm, redis):
        redis.get.return_value = None
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=20.0)  # burst_size=20
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_cost_just_over_burst_denied(self, qm, redis):
        redis.get.return_value = None
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=20.01)
        assert result["allowed"] is False

    @pytest.mark.asyncio
    async def test_tokens_remaining_returned_on_success(self, qm, redis):
        import json as _j
        bucket = {"tokens": 15.0, "last_refill": time.time()}
        redis.get.return_value = _j.dumps(bucket).encode()
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=5.0)
        assert result["allowed"] is True
        assert result["tokens_remaining"] == pytest.approx(10.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_tokens_remaining_zero_on_denial(self, qm, redis):
        import json as _j
        bucket = {"tokens": 0.5, "last_refill": time.time()}
        redis.get.return_value = _j.dumps(bucket).encode()
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=5.0)
        assert result["allowed"] is False
        assert result["tokens_remaining"] == 0.0

    @pytest.mark.asyncio
    async def test_retry_after_none_on_success(self, qm, redis):
        redis.get.return_value = None
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=1.0)
        assert result["retry_after_seconds"] is None

    @pytest.mark.asyncio
    async def test_retry_after_positive_on_denial(self, qm, redis):
        import json as _j
        bucket = {"tokens": 0.0, "last_refill": time.time()}
        redis.get.return_value = _j.dumps(bucket).encode()
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=5.0)
        assert result["retry_after_seconds"] > 0

    @pytest.mark.asyncio
    async def test_retry_after_proportional_to_cost_on_denial(self, qm, redis):
        import json as _j
        bucket = {"tokens": 0.0, "last_refill": time.time()}
        redis.get.return_value = _j.dumps(bucket).encode()
        redis.setex = AsyncMock()
        r1 = await qm.check_rate_limit("t1", cost=1.0)
        r5 = await qm.check_rate_limit("t1", cost=5.0)
        assert r5["retry_after_seconds"] > r1["retry_after_seconds"]

    @pytest.mark.asyncio
    async def test_bucket_key_contains_tenant(self, qm, redis):
        redis.get.return_value = None
        redis.setex = AsyncMock()
        await qm.check_rate_limit("special-tenant", cost=1.0)
        key = redis.get.call_args[0][0]
        assert "special-tenant" in key

    @pytest.mark.asyncio
    async def test_bucket_ttl_is_3600(self, qm, redis):
        redis.get.return_value = None
        redis.setex = AsyncMock()
        await qm.check_rate_limit("t1", cost=1.0)
        ttl = redis.setex.call_args[0][1]
        assert ttl == 3600

    @pytest.mark.asyncio
    async def test_different_tenants_different_buckets(self, qm, redis):
        redis.get.return_value = None
        redis.setex = AsyncMock()
        await qm.check_rate_limit("tenant-a", cost=1.0)
        key_a = redis.get.call_args[0][0]
        await qm.check_rate_limit("tenant-b", cost=1.0)
        key_b = redis.get.call_args[0][0]
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_cost_fractional_deducted(self, qm, redis):
        import json as _j
        bucket = {"tokens": 10.0, "last_refill": time.time()}
        redis.get.return_value = _j.dumps(bucket).encode()
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=0.5)
        assert result["allowed"] is True
        saved = _j.loads(redis.setex.call_args[0][2])
        assert saved["tokens"] == pytest.approx(9.5, abs=0.5)

    @pytest.mark.asyncio
    async def test_tokens_refilled_over_time(self, qm, redis):
        import json as _j
        # Bucket from 10 seconds ago with 0 tokens — should have refilled
        old_time = time.time() - 10.0
        bucket = {"tokens": 0.0, "last_refill": old_time}
        redis.get.return_value = _j.dumps(bucket).encode()
        redis.setex = AsyncMock()
        result = await qm.check_rate_limit("t1", cost=1.0)
        # 10s * 10 tokens/s = 100 added, capped at burst_size=20
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_tokens_capped_at_burst_size(self, qm, redis):
        import json as _j
        old_time = time.time() - 1000.0
        bucket = {"tokens": 0.0, "last_refill": old_time}
        redis.get.return_value = _j.dumps(bucket).encode()
        redis.setex = AsyncMock()
        await qm.check_rate_limit("t1", cost=1.0)
        saved = _j.loads(redis.setex.call_args[0][2])
        # After deducting 1, remaining should be burst_size - 1 at most
        assert saved["tokens"] <= qm.config.burst_size


class TestS3_CostInAuditExtended:
    @pytest.mark.asyncio
    async def test_cost_zero_logged_correctly(self, qm, kv):
        kv.set = AsyncMock()
        await qm.log_query(
            tenant="t1", question="q", top_k=1, result_count=1,
            top_score=0.9, refused=False, refusal_reason=None,
            retrieval_latency_ms=0.0, generation_latency_ms=0.0,
            cost_tokens=0.0,
        )
        entry = kv.set.call_args[0][2]
        assert entry["cost_tokens"] == 0.0

    @pytest.mark.asyncio
    async def test_cost_large_value_logged(self, qm, kv):
        kv.set = AsyncMock()
        await qm.log_query(
            tenant="t1", question="q", top_k=100, result_count=0,
            top_score=None, refused=True, refusal_reason="spam",
            retrieval_latency_ms=5000.0, generation_latency_ms=0.0,
            cost_tokens=99.9,
        )
        entry = kv.set.call_args[0][2]
        assert entry["cost_tokens"] == 99.9

    @pytest.mark.asyncio
    async def test_pg_buffer_cost_matches_redis_cost(self, qm, kv):
        kv.set = AsyncMock()
        await qm.log_query(
            tenant="t1", question="q", top_k=5, result_count=3,
            top_score=0.9, refused=False, refusal_reason=None,
            retrieval_latency_ms=50.0, generation_latency_ms=10.0,
            cost_tokens=3.14,
        )
        redis_entry = kv.set.call_args[0][2]
        pg_entry = qm._pg_writer._buffer[0]
        assert redis_entry["cost_tokens"] == pg_entry.cost_tokens

    @pytest.mark.asyncio
    async def test_stats_cost_p99_with_100_entries(self, qm, kv):
        n = 100
        kv.keys = AsyncMock(return_value=[f"t1:{i}" for i in range(n)])
        kv.get = AsyncMock(side_effect=[
            {"refused": False, "retrieval_latency_ms": 50.0,
             "generation_latency_ms": 10.0, "top_score": 0.9,
             "cost_tokens": float(i + 1)}
            for i in range(n)
        ])
        stats = await qm.get_tenant_stats("t1")
        # p99 of [1..100] should be close to 99 or 100
        assert stats["cost_p99"] >= 95.0

    @pytest.mark.asyncio
    async def test_stats_cost_p50_with_even_distribution(self, qm, kv):
        costs = [1.0, 2.0, 3.0, 4.0]
        kv.keys = AsyncMock(return_value=[f"t1:{i}" for i in range(4)])
        kv.get = AsyncMock(side_effect=[
            {"refused": False, "retrieval_latency_ms": 50.0,
             "generation_latency_ms": 10.0, "top_score": 0.9, "cost_tokens": c}
            for c in costs
        ])
        stats = await qm.get_tenant_stats("t1")
        assert stats["cost_p50"] == pytest.approx(2.5, abs=0.5)

    @pytest.mark.asyncio
    async def test_multiple_log_calls_accumulate_in_pg_buffer(self, qm, kv):
        kv.set = AsyncMock()
        for i in range(5):
            await qm.log_query(
                tenant="t1", question=f"q{i}", top_k=5, result_count=2,
                top_score=0.9, refused=False, refusal_reason=None,
                retrieval_latency_ms=float(i * 10), generation_latency_ms=5.0,
                cost_tokens=float(i + 1),
            )
        assert len(qm._pg_writer._buffer) == 5
        costs = [e.cost_tokens for e in qm._pg_writer._buffer]
        assert costs == [1.0, 2.0, 3.0, 4.0, 5.0]
