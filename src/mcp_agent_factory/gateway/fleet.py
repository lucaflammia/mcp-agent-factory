"""
Async fleet runtime — submit/poll job API and batch endpoint.

Routes
------
POST /mcp/jobs              Submit a single async job
GET  /mcp/jobs/{job_id}     Poll a single job
POST /mcp/jobs/batch        Submit N jobs as a batch
GET  /mcp/jobs/batch/{id}   Poll batch completion

Two execution backends are supported:

**Redis Streams backend** (default, local dev):
  Jobs are queued on a Redis Stream and consumed by a background FleetWorker
  running in-process. Concurrency is controlled by FLEET_CONCURRENCY. Timeout
  enforcement is asyncio.wait_for inside the worker.

**Step Functions backend** (cloud, activated when STATE_MACHINE_ARN is set):
  Submission calls sfn.start_execution. Polling calls sfn.describe_execution and
  maps the execution status to the existing pending|running|done|failed schema.
  The in-process worker loop is not started — the state machine invokes a Lambda
  worker instead. Timeout, retry, and audit trail are managed by the state machine.

The gateway API (routes, response shapes, 503 guard) is identical across both
backends.
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
STATE_MACHINE_ARN: str = os.getenv("STATE_MACHINE_ARN", "")

_STREAM = "mcp:fleet:jobs"
_GROUP = "fleet-workers"

# SFN status → fleet status mapping
_SFN_STATUS_MAP = {
    "RUNNING": "running",
    "SUCCEEDED": "done",
    "FAILED": "failed",
    "TIMED_OUT": "failed",
    "ABORTED": "failed",
}


# ---------------------------------------------------------------------------
# Redis + SFN accessors — injected at app startup from gateway/app.py
# ---------------------------------------------------------------------------

_redis: Any = None
_jobs_enabled: bool = False
_sfn_client: Any = None


def set_fleet_redis(client: Any, enabled: bool = True) -> None:
    """Inject the shared Redis client and optionally initialise the SFN client."""
    global _redis, _jobs_enabled, _sfn_client
    _redis = client
    _jobs_enabled = enabled

    if enabled and STATE_MACHINE_ARN:
        try:
            import boto3  # type: ignore[import]
            endpoint_url = os.getenv("AWS_ENDPOINT_URL")  # LocalStack or real AWS
            region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "eu-west-1"))
            _sfn_client = boto3.client(
                "stepfunctions",
                region_name=region,
                endpoint_url=endpoint_url or None,
            )
            logger.info(
                '{"event":"fleet_sfn_backend_enabled","state_machine_arn":"%s","endpoint":"%s"}',
                STATE_MACHINE_ARN,
                endpoint_url or "aws",
            )
        except Exception as exc:
            logger.warning('{"event":"fleet_sfn_client_init_failed","detail":"%s"}', exc)
            _sfn_client = None
    else:
        _sfn_client = None


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


async def _sfn_refresh_job(job: dict[str, Any]) -> dict[str, Any]:
    """Query Step Functions and sync execution status back into the job record."""
    exec_arn = job.get("execution_arn")
    if not exec_arn or not _sfn_client:
        return job

    loop = asyncio.get_event_loop()
    try:
        resp = await loop.run_in_executor(
            None,
            lambda: _sfn_client.describe_execution(executionArn=exec_arn),
        )
    except Exception as exc:
        logger.warning('{"event":"fleet_sfn_describe_error","detail":"%s"}', exc)
        return job

    sfn_status = resp.get("status", "RUNNING")
    job["status"] = _SFN_STATUS_MAP.get(sfn_status, "running")

    if sfn_status == "SUCCEEDED":
        raw_output = resp.get("output", "{}")
        try:
            job["result"] = json.loads(raw_output)
        except Exception:
            job["result"] = {"raw": raw_output}

    elif sfn_status in ("FAILED", "TIMED_OUT", "ABORTED"):
        if sfn_status == "TIMED_OUT":
            job["error"] = "timeout"
        else:
            job["error"] = resp.get("cause") or sfn_status.lower()

    await _write_job(job["job_id"], job)
    return job


async def _submit_one(method: str, params: dict[str, Any]) -> str:
    """Create a job record and dispatch to the active backend."""
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

    tracer = _otel_trace.get_tracer("mcp.fleet")
    with tracer.start_as_current_span("fleet.job.submit") as span:
        span.set_attribute("fleet.job_id", job_id)
        span.set_attribute("fleet.method", method)

        if _sfn_client and STATE_MACHINE_ARN:
            # Step Functions backend
            loop = asyncio.get_event_loop()
            try:
                resp = await loop.run_in_executor(
                    None,
                    lambda: _sfn_client.start_execution(
                        stateMachineArn=STATE_MACHINE_ARN,
                        name=job_id,
                        input=json.dumps(job),
                    ),
                )
                job["execution_arn"] = resp["executionArn"]
                job["status"] = "running"
                await _write_job(job_id, job)
                span.set_attribute("fleet.backend", "step_functions")
                logger.info(
                    '{"event":"fleet_job_sfn_started","job_id":"%s","execution_arn":"%s"}',
                    job_id,
                    resp["executionArn"],
                )
            except Exception as exc:
                job["status"] = "failed"
                job["error"] = f"SFN start_execution failed: {exc}"
                await _write_job(job_id, job)
                logger.warning('{"event":"fleet_sfn_submit_error","job_id":"%s","detail":"%s"}', job_id, exc)
        else:
            # Redis Streams backend (local dev default)
            try:
                fw = FleetWorker(_redis, _STREAM, _GROUP, "gateway")
                await fw.ensure_group()
                msg_id = await fw.publish_job(job_id, method, params)
                span.set_attribute("fleet.backend", "redis_streams")
                logger.info(
                    '{"event":"fleet_job_published","job_id":"%s","stream_msg_id":"%s"}',
                    job_id,
                    msg_id,
                )
            except Exception as exc:
                logger.warning('{"event":"fleet_publish_error","job_id":"%s","detail":"%s"}', job_id, exc)

    return job_id


# ---------------------------------------------------------------------------
# Background worker loop — only started when Redis Streams backend is active
# ---------------------------------------------------------------------------

_worker_task: asyncio.Task | None = None


async def _run_workers() -> None:
    """Spawn FLEET_CONCURRENCY workers that process jobs from the stream."""
    fw = FleetWorker(_redis, _STREAM, _GROUP, "worker-0")
    await fw.ensure_group()
    semaphore = asyncio.Semaphore(FLEET_CONCURRENCY)
    logger.info(
        '{"event":"fleet_worker_loop_started","stream":"%s","group":"%s","concurrency":%d}',
        _STREAM,
        _GROUP,
        FLEET_CONCURRENCY,
    )

    while True:
        try:
            job_msg = await fw.claim_job(block_ms=2000)
            if job_msg is None:
                await asyncio.sleep(0.05)
                continue
            msg_id, job_id = job_msg
            logger.info('{"event":"fleet_job_claimed","job_id":"%s"}', job_id)
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
                logger.warning('{"event":"fleet_job_missing","job_id":"%s"}', job_id)
                await fw.ack(msg_id)
                return

            # Mark running
            job["status"] = "running"
            await _write_job(job_id, job)
            logger.info(
                '{"event":"fleet_job_running","job_id":"%s","method":"%s"}',
                job_id,
                job.get("method", ""),
            )
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
                logger.warning(
                    '{"event":"fleet_job_failed","job_id":"%s","detail":"%s"}',
                    job_id,
                    exc,
                )

            await _write_job(job_id, job)
            await fw.ack(msg_id)
            logger.info(
                '{"event":"fleet_job_finished","job_id":"%s","status":"%s"}',
                job_id,
                job["status"],
            )


async def _execute_job(job: dict[str, Any]) -> dict[str, Any]:
    """Run the existing 4-layer pipeline for a job.

    Blocking work (PDF extraction, boto3 Bedrock calls) is already offloaded
    to threads inside AnalystAgent and BedrockHandler, so awaiting here on the
    main event loop gives true concurrency across all fleet jobs.
    """
    from mcp_agent_factory.gateway.app import _agents_dispatch
    from mcp_agent_factory.server_http import MCPRequest

    req = MCPRequest(
        jsonrpc="2.0",
        id=job["job_id"],
        method=job["method"],
        params=job.get("params", {}),
    )
    resp = await _agents_dispatch(req, None)
    resp_dict = resp.model_dump(exclude_none=True)
    if "error" in resp_dict:
        raise RuntimeError(resp_dict["error"].get("message", "dispatch error"))
    return resp_dict.get("result", {})


async def start_fleet_workers() -> None:
    """Start the background worker loop (Redis Streams backend only).

    When the Step Functions backend is active the in-process worker loop is
    not started — executions are driven by the state machine + Lambda worker.
    """
    global _worker_task
    if _redis is None:
        logger.error('{"event":"fleet_workers_skipped","reason":"redis_is_none"}')
        return
    if _sfn_client and STATE_MACHINE_ARN:
        logger.info(
            '{"event":"fleet_workers_skipped","reason":"sfn_backend_active",'
            '"state_machine_arn":"%s"}',
            STATE_MACHINE_ARN,
        )
        return
    _worker_task = asyncio.create_task(_run_workers())
    logger.info('{"event":"fleet_workers_started","concurrency":%d}', FLEET_CONCURRENCY)


async def stop_fleet_workers() -> None:
    global _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        _worker_task = None


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

_JOBS_UNAVAILABLE = {
    "error": "async_jobs_unavailable",
    "detail": (
        "The async job backend (Redis) is not configured on this deployment. "
        "Async jobs are available locally (see docker-compose.yml). "
        "Cloud support is tracked in issue #29."
    ),
}


def _require_redis() -> None:
    """Raise 503 when async jobs are not available on this deployment."""
    if not _jobs_enabled:
        raise HTTPException(status_code=503, detail=_JOBS_UNAVAILABLE)


from fastapi import Depends  # noqa: E402  (import after module-level singletons)

fleet_router = APIRouter(
    prefix="/mcp/jobs",
    tags=["fleet"],
    dependencies=[Depends(_require_redis)],
)


@fleet_router.post("", response_model=JobStatus, status_code=202)
async def submit_job(req: JobRequest) -> JobStatus:
    """Submit a single async job. Returns job_id immediately."""
    job_id = await _submit_one(req.method, req.params)
    # For SFN backend the job is immediately in running state
    job = await _read_job(job_id)
    status = job["status"] if job else "pending"
    return JobStatus(job_id=job_id, status=status)


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
            if _sfn_client and job.get("execution_arn"):
                job = await _sfn_refresh_job(job)
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


@fleet_router.get("/debug", response_model=dict)
async def fleet_debug() -> dict:
    """Diagnostic endpoint: backend type, stream/execution state, worker liveness."""
    info: dict[str, Any] = {
        "backend": "step_functions" if (_sfn_client and STATE_MACHINE_ARN) else "redis_streams",
        "worker_task_alive": _worker_task is not None and not _worker_task.done(),
    }
    if _sfn_client and STATE_MACHINE_ARN:
        info["state_machine_arn"] = STATE_MACHINE_ARN
    if _worker_task is not None and _worker_task.done():
        exc = _worker_task.exception() if not _worker_task.cancelled() else "cancelled"
        info["worker_task_error"] = str(exc)
    try:
        slen = await _redis.xlen(_STREAM)
        info["stream_length"] = slen
    except Exception as e:
        info["stream_length_error"] = str(e)
    try:
        groups = await _redis.xinfo_groups(_STREAM)
        info["consumer_groups"] = [
            {
                "name": (g[b"name"].decode() if isinstance(g.get(b"name"), bytes) else g.get("name", "")),
                "consumers": g.get(b"consumers", g.get("consumers", 0)),
                "pending": g.get(b"pending", g.get("pending", 0)),
                "last_delivered_id": (
                    g[b"last-delivered-id"].decode()
                    if isinstance(g.get(b"last-delivered-id"), bytes)
                    else g.get("last-delivered-id", "")
                ),
            }
            for g in groups
        ]
    except Exception as e:
        info["consumer_groups_error"] = str(e)
    return info


@fleet_router.get("/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    """Poll a single job by ID. Refreshes from Step Functions if SFN backend is active."""
    job = await _read_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if _sfn_client and job.get("execution_arn"):
        job = await _sfn_refresh_job(job)

    return JobStatus(
        job_id=job_id,
        status=job["status"],
        result=job.get("result"),
        error=job.get("error"),
    )
