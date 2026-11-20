"""Tests for query management — rate limiting, quotas, and audit logging."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_agent_factory.gateway.query_management import QueryManager, RateLimitConfig


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_kv_store():
    """Mock KV store."""
    store = AsyncMock()
    return store


@pytest.fixture
def query_manager(mock_redis, mock_kv_store):
    """Create a QueryManager with mocked dependencies."""
    config = RateLimitConfig(
        tokens_per_second=10.0,
        burst_size=20,
        daily_quota=1000,
        hourly_quota=100,
    )
    return QueryManager(
        kv_store=mock_kv_store,
        redis_client=mock_redis,
        config=config,
    )


@pytest.mark.asyncio
async def test_rate_limit_allows_first_request(query_manager, mock_redis):
    """First request should be allowed (bucket initialized)."""
    mock_redis.get.return_value = None  # No existing bucket
    mock_redis.setex = AsyncMock()

    result = await query_manager.check_rate_limit("tenant-1")

    assert result["allowed"] is True
    assert result["tokens_remaining"] == query_manager.config.burst_size - 1
    assert result["retry_after_seconds"] is None
    mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_rate_limit_respects_burst_size(query_manager, mock_redis):
    """Should allow burst_size requests quickly."""
    import json

    # Track stored bucket state between calls
    stored_bucket = None

    async def get_side_effect(key):
        return json.dumps(stored_bucket).encode() if stored_bucket else None

    async def setex_side_effect(key, ttl, value):
        nonlocal stored_bucket
        stored_bucket = json.loads(value)

    mock_redis.get.side_effect = get_side_effect
    mock_redis.setex.side_effect = setex_side_effect

    for i in range(query_manager.config.burst_size):
        result = await query_manager.check_rate_limit("tenant-1")
        assert result["allowed"] is True, f"Request {i} should be allowed"

    # Next request should be rate limited (burst exhausted)
    result = await query_manager.check_rate_limit("tenant-1")
    assert result["allowed"] is False
    assert result["retry_after_seconds"] is not None


@pytest.mark.asyncio
async def test_rate_limit_refills_tokens(query_manager, mock_redis):
    """Tokens should refill over time."""
    import json
    import time

    now = time.time()
    # Bucket with 0 tokens, last refilled 1 second ago
    bucket = {
        "tokens": 0.0,
        "last_refill": now - 1.0,
    }
    mock_redis.get.return_value = json.dumps(bucket).encode()
    mock_redis.setex = AsyncMock()

    result = await query_manager.check_rate_limit("tenant-1")

    # Should have ~10 tokens after 1 second (tokens_per_second=10)
    assert result["allowed"] is True
    assert result["tokens_remaining"] >= 8  # Allow for timing variation


@pytest.mark.asyncio
async def test_quota_allows_under_limit(query_manager, mock_redis):
    """Requests under quota should be allowed."""
    mock_redis.get.return_value = None
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()

    result = await query_manager.check_quota("tenant-1", quota_type="daily")

    assert result["allowed"] is True
    assert result["used"] == 1
    assert result["limit"] == query_manager.config.daily_quota


@pytest.mark.asyncio
async def test_quota_blocks_at_limit(query_manager, mock_redis):
    """Requests at quota limit should be blocked."""
    # Mock Redis returning quota at limit
    mock_redis.get.return_value = str(query_manager.config.daily_quota).encode()

    result = await query_manager.check_quota("tenant-1", quota_type="daily")

    assert result["allowed"] is False
    assert result["used"] == query_manager.config.daily_quota
    assert result["reset_in_seconds"] is not None


@pytest.mark.asyncio
async def test_quota_hourly_vs_daily(query_manager, mock_redis):
    """Hourly and daily quotas should track separately."""
    mock_redis.get.return_value = None
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()

    daily = await query_manager.check_quota("tenant-1", quota_type="daily")
    hourly = await query_manager.check_quota("tenant-1", quota_type="hourly")

    assert daily["limit"] == query_manager.config.daily_quota
    assert hourly["limit"] == query_manager.config.hourly_quota
    # Both should be allowed
    assert daily["allowed"] is True
    assert hourly["allowed"] is True


@pytest.mark.asyncio
async def test_audit_log_stores_query_metadata(query_manager, mock_kv_store):
    """Query metadata should be stored in audit log."""
    mock_kv_store.set = AsyncMock()

    entry_id = await query_manager.log_query(
        tenant="tenant-1",
        question="What is 2+2?",
        top_k=5,
        result_count=3,
        top_score=0.95,
        refused=False,
        refusal_reason=None,
        retrieval_latency_ms=42.5,
        generation_latency_ms=15.3,
    )

    assert entry_id is not None
    assert "tenant-1:" in entry_id
    mock_kv_store.set.assert_called_once()
    # Check that set was called with "audit" topic
    call_args = mock_kv_store.set.call_args
    assert call_args[0][0] == "audit"


@pytest.mark.asyncio
async def test_audit_log_truncates_long_questions(query_manager, mock_kv_store):
    """Long questions should be truncated to 500 chars."""
    mock_kv_store.set = AsyncMock()

    long_question = "x" * 1000
    await query_manager.log_query(
        tenant="tenant-1",
        question=long_question,
        top_k=5,
        result_count=0,
        top_score=None,
        refused=True,
        refusal_reason="No results",
        retrieval_latency_ms=10.0,
        generation_latency_ms=5.0,
    )

    call_args = mock_kv_store.set.call_args
    entry = call_args[0][2]
    assert len(entry["question"]) <= 500


@pytest.mark.asyncio
async def test_get_tenant_stats_aggregates_queries(query_manager, mock_kv_store):
    """Should aggregate query stats across multiple entries."""
    # Mock kv_store.keys and get
    mock_kv_store.keys.return_value = [
        "tenant-1:1234567890",
        "tenant-1:1234567891",
        "tenant-1:1234567892",
    ]

    mock_kv_store.get.side_effect = [
        {
            "refused": False,
            "retrieval_latency_ms": 100.0,
            "generation_latency_ms": 50.0,
            "top_score": 0.9,
        },
        {
            "refused": False,
            "retrieval_latency_ms": 110.0,
            "generation_latency_ms": 55.0,
            "top_score": 0.85,
        },
        {
            "refused": True,
            "retrieval_latency_ms": 50.0,
            "generation_latency_ms": 10.0,
            "top_score": 0.1,
        },
    ]

    stats = await query_manager.get_tenant_stats("tenant-1")

    assert stats["tenant"] == "tenant-1"
    assert stats["total_queries"] == 3
    assert stats["refusal_rate"] == pytest.approx(1 / 3, abs=0.01)
    assert stats["avg_retrieval_latency_ms"] == pytest.approx(86.67, abs=1.0)
    assert stats["avg_generation_latency_ms"] == pytest.approx(38.33, abs=1.0)
    assert stats["avg_top_score"] == pytest.approx(0.617, abs=0.01)
