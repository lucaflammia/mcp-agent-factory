"""
Async fleet runtime — submit/poll job API and batch endpoint.

Routes
------
POST /mcp/jobs              Submit a single async job
GET  /mcp/jobs/{job_id}     Poll a single job
POST /mcp/jobs/batch        Submit N jobs as a batch
GET  /mcp/jobs/batch/{id}   Poll batch completion

Jobs are stored in Redis as JSON under ``mcp:job:{job_id}``.
Workers are driven by ``FleetWorker``, which extends the existing
``StreamWorker`` (Redis Streams + XREADGROUP) so no second queue
framework is introduced.

Concurrency is controlled by ``FLEET_CONCURRENCY`` (default: 4).
Per-job timeout is ``FLEET_JOB_TIMEOUT_SECS`` (default: 300 s).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mcp_agent_factory.streams.fleet_worker import FleetWorker

logger = logging.getLogger(__name__)

FLEET_CONCURRENCY: int = int(os.getenv("FLEET_CONCURRENCY", "4"))
FLEET_JOB_TIMEOUT_SECS: int = int(os.getenv("FLEET_JOB_TIMEOUT_SECS", "300"))

_STREAM = "mcp:fleet:jobs"
_GROUP = "fleet-workers"


# ---------------------------------------------------------------------------
# Redis accessor — injected at app startup from gateway/app.py
# ---------------------------------------------------------------------------

_redis: Any = None


def set_fleet_redis(client: Any) -> None:
    """Inject the shared Redis client (called from app startup)."""
    global _redis
    _redis = client


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class JobRequest(BaseModel):
    method: str
    params: dict[str, Any] = {}


class BatchRequest(BaseModel):
    tasks: list[JobRequest]


class JobStatus(BaseModel):
    job_id: str
    status: str  # pending | running | done | failed
    result: dict[str, Any] | None = None
    error: str | None = None


class BatchStatus(BaseModel):
    batch_id: str
    total: int
    done: int
    failed: int
    results: list[JobStatus]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _write_job(job_id: str, data: dict[str, Any]) -> None:
    await _redis.set(f"mcp:job:{job_id}", json.dumps(data))


async def _read_job(job_id: str) -> dict[str, Any] | None:
    raw = await _redis.get(f"mcp:job:{job_id}")
    if raw is None:
        return None
    return json.loads(raw)


async def _submit_one(method: str, params: dict[str, Any]) -> str:
    """Create a job record in Redis and publish it to the fleet stream."""
    from opentelemetry import trace as _otel_trace  # type: ignore[import]
    job_id = str(uuid.uuid4())
    now = time.time()
    job: dict[str, Any] = {
        "job_id": job_id,
        "method": method,
        "params": params,
        "status": "pending",
        "created_at": now,
        "timeout_secs": FLEET_JOB_TIMEOUT_SECS,
        "result": None,
        "error": None,
    }
    await _write_job(job_id, job)

    # Publish to the stream so a FleetWorker picks it up
    tracer = _otel_trace.get_tracer("mcp.fleet")
    with tracer.start_as_current_span("fleet.job.submit") as span:
        span.set_attribute("fleet.job_id", job_id)
        span.set_attribute("fleet.method", method)
        try:
            fw = FleetWorker(_redis, _STREAM, _GROUP, "gateway")
            await fw.ensure_group()
            await fw.publish_job(job_id, method, params)
        except Exception as exc:
            logger.warning('{"event":"fleet_publish_error","job_id":"%s","detail":"%s"}', job_id, exc)
    return job_id


# ---------------------------------------------------------------------------
# Background worker loop — started once per gateway process
# ---------------------------------------------------------------------------

_worker_task: asyncio.Task | None = None


async def _run_workers() -> None:
    """Spawn FLEET_CONCURRENCY workers that process jobs from the stream."""
    fw = FleetWorker(_redis, _STREAM, _GROUP, "worker-0")
    await fw.ensure_group()
    semaphore = asyncio.Semaphore(FLEET_CONCURRENCY)

    while True:
        try:
            job_msg = await fw.claim_job()
            if job_msg is None:
                await asyncio.sleep(0.1)
                continue
            msg_id, job_id = job_msg
            asyncio.create_task(_process_job(fw, msg_id, job_id, semaphore))
        except Exception as exc:
            logger.warning('{"event":"fleet_worker_loop_error","detail":"%s"}', exc)
            await asyncio.sleep(1.0)


async def _process_job(
    fw: FleetWorker,
    msg_id: Any,
    job_id: str,
    semaphore: asyncio.Semaphore,
) -> None:
    from opentelemetry import trace as _otel_trace  # type: ignore[import]

    async with semaphore:
        tracer = _otel_trace.get_tracer("mcp.fleet")
        with tracer.start_as_current_span("fleet.job.execute") as span:
            span.set_attribute("fleet.job_id", job_id)

            job = await _read_job(job_id)
            if job is None:
                await fw.ack(msg_id)
                return

            # Mark running
            job["status"] = "running"
            await _write_job(job_id, job)
            span.set_attribute("fleet.method", job.get("method", ""))

            try:
                result = await asyncio.wait_for(
                    _execute_job(job),
                    timeout=float(job.get("timeout_secs", FLEET_JOB_TIMEOUT_SECS)),
                )
                job["status"] = "done"
                job["result"] = result
                span.set_attribute("fleet.job.outcome", "done")
            except asyncio.TimeoutError:
                job["status"] = "failed"
                job["error"] = f"Job timed out after {job.get('timeout_secs')} seconds"
                span.set_attribute("fleet.job.outcome", "timeout")
            except Exception as exc:
                job["status"] = "failed"
                job["error"] = str(exc)
                span.set_attribute("fleet.job.outcome", "failed")
                logger.warning('{"event":"fleet_job_failed","job_id":"%s","detail":"%s"}', job_id, exc)

            await _write_job(job_id, job)
            await fw.ack(msg_id)


async def _execute_job(job: dict[str, Any]) -> dict[str, Any]:
    """Run the existing 4-layer pipeline for a job in a thread pool.

    PDF extraction and embedding are synchronous and blocking. Running them
    in asyncio.to_thread keeps the event loop free so the worker can claim
    and update other jobs concurrently.
    """
    import concurrent.futures

    def _run_sync() -> dict[str, Any]:
        """Blocking wrapper that runs the async pipeline in a fresh event loop."""
        import asyncio as _asyncio
        from mcp_agent_factory.gateway.app import _agents_dispatch
        from mcp_agent_factory.server_http import MCPRequest

        req = MCPRequest(
            jsonrpc="2.0",
            id=job["job_id"],
            method=job["method"],
            params=job.get("params", {}),
        )
        loop = _asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(_agents_dispatch(req, None))
        finally:
            loop.close()

        resp_dict = resp.model_dump(exclude_none=True)
        if "error" in resp_dict:
            raise RuntimeError(resp_dict["error"].get("message", "dispatch error"))
        return resp_dict.get("result", {})

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return await loop.run_in_executor(executor, _run_sync)


async def start_fleet_workers() -> None:
    """Start the background worker loop. Called from the gateway lifespan."""
    global _worker_task
    if _redis is not None:
        _worker_task = asyncio.create_task(_run_workers())
        logger.debug('{"event":"fleet_workers_started","concurrency":%d}', FLEET_CONCURRENCY)


async def stop_fleet_workers() -> None:
    global _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        _worker_task = None


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

fleet_router = APIRouter(prefix="/mcp/jobs", tags=["fleet"])


@fleet_router.post("", response_model=JobStatus, status_code=202)
async def submit_job(req: JobRequest) -> JobStatus:
    """Submit a single async job. Returns job_id immediately."""
    job_id = await _submit_one(req.method, req.params)
    return JobStatus(job_id=job_id, status="pending")


@fleet_router.get("/batch/{batch_id}", response_model=BatchStatus)
async def get_batch(batch_id: str) -> BatchStatus:
    """Poll all jobs in a batch."""
    raw = await _redis.get(f"mcp:batch:{batch_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    job_ids: list[str] = json.loads(raw)
    results: list[JobStatus] = []
    done_count = 0
    failed_count = 0
    for jid in job_ids:
        job = await _read_job(jid)
        if job is None:
            status = JobStatus(job_id=jid, status="failed", error="job record missing")
        else:
            status = JobStatus(
                job_id=jid,
                status=job["status"],
                result=job.get("result"),
                error=job.get("error"),
            )
        results.append(status)
        if status.status == "done":
            done_count += 1
        elif status.status == "failed":
            failed_count += 1
    return BatchStatus(
        batch_id=batch_id,
        total=len(job_ids),
        done=done_count,
        failed=failed_count,
        results=results,
    )


@fleet_router.post("/batch", response_model=dict)
async def submit_batch(req: BatchRequest) -> dict:
    """Submit N tasks as a batch. Returns batch_id and all job_ids immediately."""
    batch_id = str(uuid.uuid4())
    job_ids: list[str] = []
    for task in req.tasks:
        job_id = await _submit_one(task.method, task.params)
        job_ids.append(job_id)
    await _redis.set(f"mcp:batch:{batch_id}", json.dumps(job_ids))
    return {"batch_id": batch_id, "job_ids": job_ids}


@fleet_router.get("/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    """Poll a single job by ID."""
    job = await _read_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        result=job.get("result"),
        error=job.get("error"),
    )
