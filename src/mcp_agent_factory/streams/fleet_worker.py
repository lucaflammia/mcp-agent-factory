"""
FleetWorker — async extension of StreamWorker for the fleet job queue.

Extends the XREADGROUP pattern from StreamWorker with:
  - async/await interface (uses redis.asyncio)
  - job-specific publish/claim that carries job_id + method + params
  - ensure_group() creates the consumer group if absent (BUSYGROUP ignored)
"""
from __future__ import annotations

import json
import logging
from typing import Any

from redis.exceptions import ResponseError

logger = logging.getLogger(__name__)


class FleetWorker:
    """Async consumer-group worker for the fleet job queue."""

    def __init__(self, client: Any, stream: str, group: str, consumer: str) -> None:
        self._client = client
        self._stream = stream
        self._group = group
        self._consumer = consumer

    async def ensure_group(self) -> None:
        try:
            await self._client.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def publish_job(self, job_id: str, method: str, params: dict[str, Any]) -> str:
        fields = {
            "job_id": job_id,
            "method": method,
            "params": json.dumps(params),
        }
        msg_id = await self._client.xadd(self._stream, fields)
        logger.debug(
            '{"event":"fleet_publish","stream":"%s","job_id":"%s"}',
            self._stream, job_id,
        )
        return msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)

    async def claim_job(self) -> tuple[Any, str] | None:
        """Claim the next pending job. Returns (msg_id, job_id) or None."""
        result = await self._client.xreadgroup(
            self._group,
            self._consumer,
            streams={self._stream: ">"},
            count=1,
        )
        if not result:
            return None
        messages = result[0][1]
        if not messages:
            return None
        msg_id, fields = messages[0]
        job_id = fields.get(b"job_id", fields.get("job_id", b"")).decode() if isinstance(
            fields.get(b"job_id", fields.get("job_id", b"")), bytes
        ) else fields.get(b"job_id", fields.get("job_id", ""))
        if isinstance(job_id, bytes):
            job_id = job_id.decode()
        logger.debug(
            '{"event":"fleet_claim","stream":"%s","job_id":"%s"}',
            self._stream, job_id,
        )
        return msg_id, job_id

    async def ack(self, msg_id: Any) -> None:
        await self._client.xack(self._stream, self._group, msg_id)
        logger.debug(
            '{"event":"fleet_ack","stream":"%s","msg_id":"%s"}',
            self._stream, msg_id,
        )
