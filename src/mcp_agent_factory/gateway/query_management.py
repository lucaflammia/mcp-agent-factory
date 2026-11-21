"""Query management — rate limiting, quotas, audit logging, timezone support, cost-based limiting.

RAG-08: token-bucket rate limiting, Redis quotas, 24h audit log
RAG-09 enhancements:
  S1 — PostgreSQL-backed durable audit log with async batch writer
  S2 — Per-tenant timezone-aware quota windows (DST-safe)
  S3 — Variable query cost (top_k, latency, retries, refusals)
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

logger = logging.getLogger("mcp_gateway")

# ---------------------------------------------------------------------------
# Cost weights (all tunable via env vars in app.py)
# ---------------------------------------------------------------------------
DEFAULT_COST_TOP_K_PER_UNIT: float = 0.1    # extra cost per top_k beyond 1
DEFAULT_COST_LATENCY_MS_PER_100: float = 0.1 # extra cost per 100ms retrieval
DEFAULT_COST_REFUSAL_PENALTY: float = 0.5    # extra cost on refused queries
DEFAULT_COST_RETRY_PENALTY: float = 0.25     # extra cost per retry

VALID_TIMEZONES: frozenset[str] = frozenset()  # filled lazily below


def _load_valid_timezones() -> frozenset[str]:
    global VALID_TIMEZONES
    if VALID_TIMEZONES:
        return VALID_TIMEZONES
    try:
        import zoneinfo
        VALID_TIMEZONES = frozenset(zoneinfo.available_timezones())
    except Exception:
        # Minimal fallback for environments without zoneinfo
        VALID_TIMEZONES = frozenset(["UTC"])
    return VALID_TIMEZONES


def is_valid_timezone(tz: str) -> bool:
    if tz == "UTC":
        return True
    try:
        import zoneinfo
        zoneinfo.ZoneInfo(tz)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class RateLimitConfig:
    """Rate limit configuration per tenant."""

    tokens_per_second: float = 10.0
    burst_size: int = 20
    daily_quota: int = 100_000
    hourly_quota: int = 10_000
    # RAG-09 S3: cost weights
    cost_top_k_per_unit: float = DEFAULT_COST_TOP_K_PER_UNIT
    cost_latency_ms_per_100: float = DEFAULT_COST_LATENCY_MS_PER_100
    cost_refusal_penalty: float = DEFAULT_COST_REFUSAL_PENALTY
    cost_retry_penalty: float = DEFAULT_COST_RETRY_PENALTY


@dataclass
class TenantConfig:
    """Per-tenant configuration including timezone (RAG-09 S2).

    Quota fields default to 0, meaning "use global config default".
    """

    tenant: str
    timezone: str = "UTC"
    daily_quota: int = 0   # 0 = use global config
    hourly_quota: int = 0  # 0 = use global config
    tokens_per_second: float = 0.0  # 0 = use global config
    burst_size: int = 0    # 0 = use global config


@dataclass
class AuditEntry:
    """A single audit log entry."""

    entry_id: str
    tenant: str
    question: str
    top_k: int
    result_count: int
    top_score: float | None
    refused: bool
    refusal_reason: str | None
    retrieval_ms: float
    generation_ms: float
    cost_tokens: float
    timestamp: str  # ISO-8601


# ---------------------------------------------------------------------------
# Cost calculator (RAG-09 S3)
# ---------------------------------------------------------------------------

def calculate_query_cost(
    top_k: int,
    retrieval_ms: float,
    refused: bool,
    retries: int = 0,
    *,
    cfg: RateLimitConfig | None = None,
) -> float:
    """
    Compute variable token cost for a query.

    Base cost is 1.0. Additional cost components:
      - top_k beyond 1: each unit adds cost_top_k_per_unit
      - retrieval latency: each 100ms adds cost_latency_ms_per_100
      - refusal penalty applied once if refused
      - retry penalty applied per retry
    """
    if cfg is None:
        cfg = RateLimitConfig()
    cost = 1.0
    cost += max(0, top_k - 1) * cfg.cost_top_k_per_unit
    cost += (retrieval_ms / 100.0) * cfg.cost_latency_ms_per_100
    if refused:
        cost += cfg.cost_refusal_penalty
    cost += retries * cfg.cost_retry_penalty
    return round(cost, 4)


# ---------------------------------------------------------------------------
# Timezone-aware quota window (RAG-09 S2)
# ---------------------------------------------------------------------------

def _quota_window_key(quota_type: Literal["daily", "hourly"], tz_name: str) -> str:
    """
    Return the Redis key suffix for the current quota window in the
    given timezone. DST-safe: uses zoneinfo.ZoneInfo when available.
    """
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tz_name)
        now_local = datetime.now(tz=tz)
    except Exception:
        now_local = datetime.now(tz=timezone.utc)

    if quota_type == "daily":
        return now_local.strftime("%Y-%m-%d")
    return now_local.strftime("%Y-%m-%d-%H")


def _quota_reset_seconds(quota_type: Literal["daily", "hourly"], tz_name: str) -> float:
    """Return seconds until the next quota window resets in the given timezone."""
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tz_name)
        now_local = datetime.now(tz=tz)
    except Exception:
        now_local = datetime.now(tz=timezone.utc)

    if quota_type == "daily":
        next_reset = (now_local + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:
        next_reset = (now_local + timedelta(hours=1)).replace(
            minute=0, second=0, microsecond=0
        )
    delta = (next_reset - now_local).total_seconds()
    return max(0.0, delta)


# ---------------------------------------------------------------------------
# Async PostgreSQL batch writer (RAG-09 S1)
# ---------------------------------------------------------------------------

class AsyncAuditWriter:
    """
    Batches audit entries and flushes to PostgreSQL asynchronously.

    Flush triggers:
      - Every ``flush_interval`` seconds
      - When the buffer reaches ``max_buffer`` entries

    Falls back gracefully if PostgreSQL is unavailable.
    """

    def __init__(
        self,
        pg_pool: Any,  # asyncpg Pool or None
        flush_interval: float = 10.0,
        max_buffer: int = 1000,
    ) -> None:
        self._pool = pg_pool
        self._flush_interval = flush_interval
        self._max_buffer = max_buffer
        self._buffer: list[AuditEntry] = []
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._pool is not None and self._task is None:
            self._task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._flush()

    async def enqueue(self, entry: AuditEntry) -> None:
        async with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) >= self._max_buffer:
                await self._flush_locked()

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self._flush_interval)
            await self._flush()

    async def _flush(self) -> None:
        async with self._lock:
            await self._flush_locked()

    async def _flush_locked(self) -> None:
        if not self._buffer or self._pool is None:
            return
        entries, self._buffer = self._buffer, []
        success = False
        try:
            async with self._pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO query_audit_log
                        (tenant, question, top_k, result_count, top_score,
                         refused, refusal_reason, retrieval_ms, generation_ms,
                         cost_tokens, timestamp)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::timestamptz)
                    """,
                    [
                        (
                            e.tenant, e.question, e.top_k, e.result_count,
                            e.top_score, e.refused, e.refusal_reason,
                            e.retrieval_ms, e.generation_ms, e.cost_tokens,
                            e.timestamp,
                        )
                        for e in entries
                    ],
                )
            success = True
        except Exception as exc:
            logger.warning(json.dumps({
                "event": "audit_pg_flush_failed",
                "count": len(entries),
                "detail": str(exc),
            }))
        if not success:
            # Return entries to buffer — called with lock held, so extend directly
            self._buffer = entries + self._buffer

    async def export(
        self,
        tenant: str,
        start: datetime,
        end: datetime,
        fmt: Literal["json", "csv"] = "json",
    ) -> str:
        """Export audit logs for a tenant within a date range."""
        if self._pool is None:
            return "[]" if fmt == "json" else "tenant,timestamp,question,refused,cost_tokens\n"

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT tenant, question, top_k, result_count, top_score,
                       refused, refusal_reason, retrieval_ms, generation_ms,
                       cost_tokens, timestamp
                FROM   query_audit_log
                WHERE  tenant = $1
                  AND  timestamp >= $2
                  AND  timestamp <  $3
                ORDER  BY timestamp ASC
                """,
                tenant, start, end,
            )

        if fmt == "json":
            return json.dumps([dict(r) for r in rows], default=str)

        # CSV
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=[
            "tenant", "question", "top_k", "result_count", "top_score",
            "refused", "refusal_reason", "retrieval_ms", "generation_ms",
            "cost_tokens", "timestamp",
        ])
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
        return buf.getvalue()


# ---------------------------------------------------------------------------
# QueryManager
# ---------------------------------------------------------------------------

class QueryManager:
    """
    Manages rate limiting, quotas, audit logging, timezone support,
    and cost-based limiting for gateway queries.

    RAG-08: token-bucket rate limit, Redis quotas, 24h audit log
    RAG-09:
      S1 — async PostgreSQL batch writer for durable audit history
      S2 — per-tenant timezone-aware quota windows (DST-safe)
      S3 — variable query cost; rate limiter deducts variable tokens
    """

    def __init__(
        self,
        kv_store: Any,
        redis_client: Any,
        config: RateLimitConfig | None = None,
        audit_log_ttl_seconds: int = 86400,
        pg_pool: Any = None,
        audit_flush_interval: float = 10.0,
        audit_max_buffer: int = 1000,
    ) -> None:
        self.kv_store = kv_store
        self.redis = redis_client
        self.config = config or RateLimitConfig()
        self.audit_log_ttl = audit_log_ttl_seconds
        self._tenant_configs: dict[str, TenantConfig] = {}

        # RAG-09 S1: async PostgreSQL writer
        self._pg_writer = AsyncAuditWriter(
            pg_pool=pg_pool,
            flush_interval=audit_flush_interval,
            max_buffer=audit_max_buffer,
        )

    def start(self) -> None:
        """Start background flush loop. Call from lifespan startup."""
        self._pg_writer.start()

    async def stop(self) -> None:
        """Flush remaining buffer. Call from lifespan shutdown."""
        await self._pg_writer.stop()

    # ------------------------------------------------------------------
    # Tenant config (RAG-09 S2)
    # ------------------------------------------------------------------

    def set_tenant_config(self, cfg: TenantConfig) -> None:
        self._tenant_configs[cfg.tenant] = cfg

    def get_tenant_config(self, tenant: str) -> TenantConfig:
        return self._tenant_configs.get(tenant, TenantConfig(tenant=tenant))

    def _tenant_tz(self, tenant: str) -> str:
        return self.get_tenant_config(tenant).timezone

    # ------------------------------------------------------------------
    # Rate limiting (token bucket — RAG-08 + RAG-09 S3 variable cost)
    # ------------------------------------------------------------------

    async def check_rate_limit(
        self,
        tenant: str,
        cost: float = 1.0,
    ) -> dict[str, Any]:
        """
        Check rate limit and deduct ``cost`` tokens (RAG-09 S3).

        Returns:
          allowed, tokens_remaining, retry_after_seconds
        """
        key = f"ratelimit:{tenant}:bucket"
        now = time.time()

        raw = await self.redis.get(key)
        if raw is None:
            bucket = {"tokens": float(self.config.burst_size), "last_refill": now}
        else:
            bucket = json.loads(raw.decode() if isinstance(raw, bytes) else raw)

        time_passed = now - bucket["last_refill"]
        tokens_added = time_passed * self.config.tokens_per_second
        bucket["tokens"] = min(float(self.config.burst_size), bucket["tokens"] + tokens_added)
        bucket["last_refill"] = now

        if bucket["tokens"] >= cost:
            bucket["tokens"] -= cost
            await self.redis.setex(key, 3600, json.dumps(bucket))
            return {
                "allowed": True,
                "tokens_remaining": bucket["tokens"],
                "retry_after_seconds": None,
            }

        time_to_next_token = cost / self.config.tokens_per_second
        await self.redis.setex(key, 3600, json.dumps(bucket))
        return {
            "allowed": False,
            "tokens_remaining": 0.0,
            "retry_after_seconds": time_to_next_token,
        }

    # ------------------------------------------------------------------
    # Quota (RAG-08 + RAG-09 S2 timezone-aware)
    # ------------------------------------------------------------------

    async def check_quota(
        self,
        tenant: str,
        quota_type: Literal["daily", "hourly"] = "daily",
    ) -> dict[str, Any]:
        """
        Check quota using the tenant's configured timezone (RAG-09 S2).

        Returns:
          allowed, used, limit, reset_in_seconds
        """
        tc = self.get_tenant_config(tenant)
        if quota_type == "daily":
            limit = tc.daily_quota or self.config.daily_quota
            window_seconds = 86400
        elif quota_type == "hourly":
            limit = tc.hourly_quota or self.config.hourly_quota
            window_seconds = 3600
        else:
            raise ValueError(f"Unknown quota type: {quota_type}")

        tz_name = self._tenant_tz(tenant)
        window_key = _quota_window_key(quota_type, tz_name)
        key = f"quota:{tenant}:{quota_type}:{window_key}"

        raw = await self.redis.get(key)
        used = int(raw.decode() if isinstance(raw, bytes) else raw) if raw else 0

        if used >= limit:
            reset_in = _quota_reset_seconds(quota_type, tz_name)
            return {
                "allowed": False,
                "used": used,
                "limit": limit,
                "reset_in_seconds": reset_in,
            }

        await self.redis.incr(key)
        await self.redis.expire(key, window_seconds)

        return {
            "allowed": True,
            "used": used + 1,
            "limit": limit,
            "reset_in_seconds": _quota_reset_seconds(quota_type, tz_name),
        }

    # ------------------------------------------------------------------
    # Audit logging (RAG-08 Redis + RAG-09 S1 PostgreSQL)
    # ------------------------------------------------------------------

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
        cost_tokens: float = 1.0,
    ) -> str:
        """
        Log a query to Redis (real-time stats) and PostgreSQL (durable history).

        Returns the audit entry ID.
        """
        entry_id = f"{tenant}:{int(time.time() * 1000)}"
        ts = datetime.now(tz=timezone.utc).isoformat()
        entry = AuditEntry(
            entry_id=entry_id,
            tenant=tenant,
            question=question[:500],
            top_k=top_k,
            result_count=result_count,
            top_score=top_score,
            refused=refused,
            refusal_reason=refusal_reason,
            retrieval_ms=retrieval_latency_ms,
            generation_ms=generation_latency_ms,
            cost_tokens=cost_tokens,
            timestamp=ts,
        )

        # Redis (24h real-time)
        try:
            await self.kv_store.set("audit", entry_id, {
                "entry_id": entry_id,
                "tenant": tenant,
                "question": entry.question,
                "top_k": top_k,
                "result_count": result_count,
                "top_score": top_score,
                "refused": refused,
                "refusal_reason": refusal_reason,
                "retrieval_latency_ms": retrieval_latency_ms,
                "generation_latency_ms": generation_latency_ms,
                "cost_tokens": cost_tokens,
                "timestamp": ts,
            })
        except Exception as exc:
            logger.warning(json.dumps({
                "event": "audit_redis_failed",
                "entry_id": entry_id,
                "detail": str(exc),
            }))

        # PostgreSQL (durable — async batch)
        await self._pg_writer.enqueue(entry)

        logger.info(json.dumps({
            "event": "query_logged",
            "entry_id": entry_id,
            "tenant": tenant,
            "refused": refused,
            "cost_tokens": cost_tokens,
            "retrieval_ms": retrieval_latency_ms,
        }))

        return entry_id

    # ------------------------------------------------------------------
    # Stats (RAG-08 unchanged)
    # ------------------------------------------------------------------

    async def get_tenant_stats(self, tenant: str) -> dict[str, Any]:
        """Get aggregated stats for a tenant (last 24h, from Redis)."""
        entries = await self.kv_store.keys("audit")
        tenant_entries = [e for e in entries if e.startswith(f"{tenant}:")]

        if not tenant_entries:
            return {
                "tenant": tenant,
                "total_queries": 0,
                "refusal_rate": 0.0,
                "avg_retrieval_latency_ms": 0.0,
                "avg_generation_latency_ms": 0.0,
                "cost_p50": 0.0,
                "cost_p99": 0.0,
            }

        stats: dict[str, Any] = {
            "total_queries": 0,
            "refused": 0,
            "total_retrieval_ms": 0.0,
            "total_generation_ms": 0.0,
            "scores": [],
            "costs": [],
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
            stats["costs"].append(entry.get("cost_tokens", 1.0))

        n = stats["total_queries"]
        costs = sorted(stats["costs"])

        def _percentile(lst: list[float], p: float) -> float:
            if not lst:
                return 0.0
            k = (len(lst) - 1) * p
            lo, hi = int(k), math.ceil(k)
            if lo == hi:
                return lst[lo]
            return lst[lo] + (lst[hi] - lst[lo]) * (k - lo)

        return {
            "tenant": tenant,
            "total_queries": n,
            "refusal_rate": stats["refused"] / n if n > 0 else 0.0,
            "avg_retrieval_latency_ms": stats["total_retrieval_ms"] / n if n > 0 else 0.0,
            "avg_generation_latency_ms": stats["total_generation_ms"] / n if n > 0 else 0.0,
            "avg_top_score": (
                sum(stats["scores"]) / len(stats["scores"]) if stats["scores"] else 0.0
            ),
            "cost_p50": _percentile(costs, 0.5),
            "cost_p99": _percentile(costs, 0.99),
        }

    # ------------------------------------------------------------------
    # Durable export (RAG-09 S1)
    # ------------------------------------------------------------------

    async def export_audit(
        self,
        tenant: str,
        start: datetime,
        end: datetime,
        fmt: Literal["json", "csv"] = "json",
    ) -> str:
        """Export durable audit logs from PostgreSQL for a date range."""
        return await self._pg_writer.export(tenant, start, end, fmt)
