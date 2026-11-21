"""Query management — rate limiting, quotas, and audit logging.

Provides:
  - Per-tenant rate limiting (token bucket algorithm)
  - Per-tenant daily/hourly quotas
  - Query audit log for post-hoc analysis
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("mcp_gateway")


@dataclass
class RateLimitConfig:
    """Rate limit configuration per tenant."""

    tokens_per_second: float = 10.0  # 10 QPS by default
    burst_size: int = 20  # Allow burst of 20 requests
    daily_quota: int = 100_000  # 100k queries/day
    hourly_quota: int = 10_000  # 10k queries/hour


class QueryManager:
    """
    Manages rate limiting, quotas, and audit logging for queries.

    Rate limiting uses Redis-backed token bucket per tenant.
    Quotas are tracked per tenant and reset daily/hourly.
    Audit log stores query metadata for analysis.
    """

    def __init__(
        self,
        kv_store: Any,
        redis_client: Any,
        config: RateLimitConfig | None = None,
        audit_log_ttl_seconds: int = 86400,  # 24 hours
    ) -> None:
        self.kv_store = kv_store
        self.redis = redis_client
        self.config = config or RateLimitConfig()
        self.audit_log_ttl = audit_log_ttl_seconds

    async def check_rate_limit(self, tenant: str) -> dict[str, Any]:
        """
        Check if tenant has exceeded rate limit (token bucket).

        Returns dict with:
          - allowed: bool
          - tokens_remaining: float
          - retry_after_seconds: float | None
        """
        key = f"ratelimit:{tenant}:bucket"
        now = time.time()

        # Get current bucket state from Redis
        raw = await self.redis.get(key)
        if raw is None:
            # First request — initialize bucket
            bucket = {
                "tokens": self.config.burst_size,
                "last_refill": now,
            }
        else:
            bucket = json.loads(raw.decode() if isinstance(raw, bytes) else raw)

        # Refill tokens based on time elapsed
        time_passed = now - bucket["last_refill"]
        tokens_added = time_passed * self.config.tokens_per_second
        bucket["tokens"] = min(self.config.burst_size, bucket["tokens"] + tokens_added)
        bucket["last_refill"] = now

        # Check if we have at least 1 token
        if bucket["tokens"] >= 1.0:
            bucket["tokens"] -= 1.0
            await self.redis.setex(key, 3600, json.dumps(bucket))  # Persist for 1 hour
            return {
                "allowed": True,
                "tokens_remaining": bucket["tokens"],
                "retry_after_seconds": None,
            }

        # Rate limited — calculate backoff
        time_to_next_token = 1.0 / self.config.tokens_per_second
        await self.redis.setex(key, 3600, json.dumps(bucket))
        return {
            "allowed": False,
            "tokens_remaining": 0.0,
            "retry_after_seconds": time_to_next_token,
        }

    async def check_quota(self, tenant: str, quota_type: str = "daily") -> dict[str, Any]:
        """
        Check if tenant has exceeded quota (daily or hourly).

        Returns dict with:
          - allowed: bool
          - used: int
          - limit: int
          - reset_in_seconds: float
        """
        if quota_type == "daily":
            limit = self.config.daily_quota
            window_seconds = 86400
        elif quota_type == "hourly":
            limit = self.config.hourly_quota
            window_seconds = 3600
        else:
            raise ValueError(f"Unknown quota type: {quota_type}")

        # Key includes today's date (UTC) or current hour
        now = datetime.utcnow()
        if quota_type == "daily":
            window_key = now.strftime("%Y-%m-%d")
        else:
            window_key = now.strftime("%Y-%m-%d-%H")

        key = f"quota:{tenant}:{quota_type}:{window_key}"
        raw = await self.redis.get(key)
        used = int(raw.decode() if isinstance(raw, bytes) else raw) if raw else 0

        if used >= limit:
            # Calculate when quota resets
            if quota_type == "daily":
                reset_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                reset_time += timedelta(days=1)
            else:
                reset_time = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
                reset_time += timedelta(hours=1)

            reset_in = (reset_time - datetime.utcnow()).total_seconds()
            return {
                "allowed": False,
                "used": used,
                "limit": limit,
                "reset_in_seconds": max(0, reset_in),
            }

        # Increment usage
        await self.redis.incr(key)
        await self.redis.expire(key, window_seconds)

        return {
            "allowed": True,
            "used": used + 1,
            "limit": limit,
            "reset_in_seconds": window_seconds,
        }

    async def log_query(
        self,
        tenant: str,
        question: str,
        top_k: int,
        result_count: int,
        top_score: float | None,
        refused: bool,
        refusal_reason: str | None,
        retrieval_latency_ms: float,
        generation_latency_ms: float,
    ) -> str:
        """
        Log a query to the audit trail.

        Returns the audit entry ID.
        """
        entry_id = f"{tenant}:{int(time.time() * 1000)}"
        entry = {
            "entry_id": entry_id,
            "tenant": tenant,
            "question": question[:500],  # Truncate for storage
            "top_k": top_k,
            "result_count": result_count,
            "top_score": top_score,
            "refused": refused,
            "refusal_reason": refusal_reason,
            "retrieval_latency_ms": retrieval_latency_ms,
            "generation_latency_ms": generation_latency_ms,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Store in KV store under "audit" topic
        try:
            await self.kv_store.set("audit", entry_id, entry)
        except Exception as exc:
            logger.warning(
                json.dumps({
                    "event": "audit_log_failed",
                    "entry_id": entry_id,
                    "detail": str(exc),
                })
            )

        # Also emit structured log for immediate visibility
        logger.info(json.dumps({
            "event": "query_logged",
            **entry,
        }))

        return entry_id

    async def get_tenant_stats(self, tenant: str) -> dict[str, Any]:
        """Get aggregated stats for a tenant (last 24h)."""
        entries = await self.kv_store.keys("audit")
        tenant_entries = [
            e for e in entries
            if e.startswith(f"{tenant}:")
        ]

        if not tenant_entries:
            return {
                "tenant": tenant,
                "total_queries": 0,
                "refusal_rate": 0.0,
                "avg_retrieval_latency_ms": 0.0,
                "avg_generation_latency_ms": 0.0,
            }

        # Fetch entries and aggregate
        stats = {
            "total_queries": 0,
            "refused": 0,
            "total_retrieval_ms": 0.0,
            "total_generation_ms": 0.0,
            "avg_top_score": 0.0,
            "scores": [],
        }

        for entry_id in tenant_entries:
            entry = await self.kv_store.get("audit", entry_id)
            if not entry:
                continue

            stats["total_queries"] += 1
            if entry.get("refused"):
                stats["refused"] += 1
            stats["total_retrieval_ms"] += entry.get("retrieval_latency_ms", 0.0)
            stats["total_generation_ms"] += entry.get("generation_latency_ms", 0.0)
            if entry.get("top_score") is not None:
                stats["scores"].append(entry["top_score"])

        return {
            "tenant": tenant,
            "total_queries": stats["total_queries"],
            "refusal_rate": (
                stats["refused"] / stats["total_queries"]
                if stats["total_queries"] > 0
                else 0.0
            ),
            "avg_retrieval_latency_ms": (
                stats["total_retrieval_ms"] / stats["total_queries"]
                if stats["total_queries"] > 0
                else 0.0
            ),
            "avg_generation_latency_ms": (
                stats["total_generation_ms"] / stats["total_queries"]
                if stats["total_queries"] > 0
                else 0.0
            ),
            "avg_top_score": (
                sum(stats["scores"]) / len(stats["scores"])
                if stats["scores"]
                else 0.0
            ),
        }
