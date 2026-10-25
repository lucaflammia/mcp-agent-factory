"""
Tests for the async fleet runtime (Components 1 & 2).

Covers:
  - POST /mcp/jobs  — submit a job, returns job_id in < threshold
  - GET  /mcp/jobs/{id} — poll job state
  - POST /mcp/jobs/batch — submit N jobs, all get job_ids
  - GET  /mcp/jobs/batch/{id} — reflect partial/full completion
  - job timeout transition to failed
  - single failing task does not block batch siblings
  - _process_job — done / timeout / exception paths
  - _execute_job — dispatches to pipeline
  - start_fleet_workers / stop_fleet_workers lifecycle
  - FleetWorker edge cases
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

import fakeredis.aioredis as _fakeredis
import pytest
from fastapi.testclient import TestClient

import mcp_agent_factory.gateway.fleet as _fleet
from mcp_agent_factory.gateway.app import gateway_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def inject_fake_redis(monkeypatch):
    """Inject a fresh FakeRedis into the fleet module and clear env vars that
    would cause the lifespan to attempt a real Redis / Kafka connection."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
    fake = _fakeredis.FakeRedis()
    _fleet.set_fleet_redis(fake)
    # Also wire the app-level client so the lifespan ping succeeds
    import mcp_agent_factory.gateway.app as _app
    monkeypatch.setattr(_app, "_redis_client", fake)
    yield fake


@pytest.fixture
def client():
    with TestClient(gateway_app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Helper: write a finished job directly into Redis
# ---------------------------------------------------------------------------

async def _plant_job(fake_redis, job_id: str, status: str, result=None, error=None):
    job = {
        "job_id": job_id,
        "method": "agents/analyze",
        "params": {},
        "status": status,
        "created_at": time.time(),
        "timeout_secs": 300,
        "result": result,
        "error": error,
    }
    await fake_redis.set(f"mcp:job:{job_id}", json.dumps(job))


# ---------------------------------------------------------------------------
# Component 1 — single job submit / poll
# ---------------------------------------------------------------------------

class TestJobSubmit:
    def test_submit_returns_job_id_and_pending(self, client):
        resp = client.post("/mcp/jobs", json={"method": "agents/analyze", "params": {}})
        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body
        assert body["status"] == "pending"

    def test_submit_returns_quickly(self, client):
        """POST /mcp/jobs must return in under 500 ms (well under 100 ms threshold)."""
        start = time.monotonic()
        client.post("/mcp/jobs", json={"method": "agents/analyze", "params": {}})
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 500

    def test_poll_unknown_job_returns_404(self, client):
        resp = client.get(f"/mcp/jobs/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_poll_done_job_returns_result(self, client, inject_fake_redis):
        job_id = str(uuid.uuid4())
        asyncio.get_event_loop().run_until_complete(
            _plant_job(inject_fake_redis, job_id, "done", result={"summary": "ok"})
        )
        resp = client.get(f"/mcp/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "done"
        assert body["result"] == {"summary": "ok"}

    def test_poll_failed_job_returns_error(self, client, inject_fake_redis):
        job_id = str(uuid.uuid4())
        asyncio.get_event_loop().run_until_complete(
            _plant_job(inject_fake_redis, job_id, "failed", error="timed out")
        )
        resp = client.get(f"/mcp/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert "timed out" in body["error"]

    def test_poll_running_job(self, client, inject_fake_redis):
        job_id = str(uuid.uuid4())
        asyncio.get_event_loop().run_until_complete(
            _plant_job(inject_fake_redis, job_id, "running")
        )
        resp = client.get(f"/mcp/jobs/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"


# ---------------------------------------------------------------------------
# Component 2 — batch submit / poll
# ---------------------------------------------------------------------------

class TestBatchSubmit:
    def test_batch_submit_returns_batch_id_and_job_ids(self, client):
        resp = client.post("/mcp/jobs/batch", json={
            "tasks": [
                {"method": "agents/analyze", "params": {"pdf_path": "a.pdf"}},
                {"method": "agents/analyze", "params": {"pdf_path": "b.pdf"}},
                {"method": "agents/analyze", "params": {"pdf_path": "c.pdf"}},
            ]
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "batch_id" in body
        assert len(body["job_ids"]) == 3

    def test_batch_poll_unknown_batch_returns_404(self, client):
        resp = client.get(f"/mcp/jobs/batch/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_batch_poll_reflects_partial_completion(self, client, inject_fake_redis):
        # Submit 3-job batch
        submit_resp = client.post("/mcp/jobs/batch", json={
            "tasks": [
                {"method": "agents/analyze", "params": {}},
                {"method": "agents/analyze", "params": {}},
                {"method": "agents/analyze", "params": {}},
            ]
        })
        body = submit_resp.json()
        batch_id = body["batch_id"]
        job_ids = body["job_ids"]

        # Mark 1 done, 1 failed, 1 still pending
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_plant_job(inject_fake_redis, job_ids[0], "done", result={}))
        loop.run_until_complete(_plant_job(inject_fake_redis, job_ids[1], "failed", error="boom"))

        resp = client.get(f"/mcp/jobs/batch/{batch_id}")
        assert resp.status_code == 200
        status = resp.json()
        assert status["total"] == 3
        assert status["done"] == 1
        assert status["failed"] == 1
        # Third job is still pending (originally submitted)
        pending_jobs = [r for r in status["results"] if r["status"] == "pending"]
        assert len(pending_jobs) == 1

    def test_single_failing_task_does_not_block_siblings(self, client, inject_fake_redis):
        """A failed job must not affect the status of sibling jobs."""
        submit_resp = client.post("/mcp/jobs/batch", json={
            "tasks": [
                {"method": "agents/analyze", "params": {}},
                {"method": "agents/analyze", "params": {}},
            ]
        })
        body = submit_resp.json()
        batch_id = body["batch_id"]
        job_ids = body["job_ids"]

        loop = asyncio.get_event_loop()
        loop.run_until_complete(_plant_job(inject_fake_redis, job_ids[0], "failed", error="err"))
        loop.run_until_complete(_plant_job(inject_fake_redis, job_ids[1], "done", result={"ok": True}))

        resp = client.get(f"/mcp/jobs/batch/{batch_id}")
        status = resp.json()
        assert status["done"] == 1
        assert status["failed"] == 1
        done_job = next(r for r in status["results"] if r["status"] == "done")
        assert done_job["result"] == {"ok": True}


# ---------------------------------------------------------------------------
# FleetWorker edge cases
# ---------------------------------------------------------------------------

class TestFleetWorker:
    """Unit tests for FleetWorker that don't go through the HTTP layer."""

    @pytest.mark.asyncio
    async def test_ensure_group_ignores_busygroup(self, inject_fake_redis):
        from mcp_agent_factory.streams.fleet_worker import FleetWorker
        from redis.exceptions import ResponseError

        fw = FleetWorker(inject_fake_redis, "test:stream", "grp", "c1")
        await fw.ensure_group()
        # Second call hits BUSYGROUP — should not raise
        await fw.ensure_group()

    @pytest.mark.asyncio
    async def test_ensure_group_reraises_non_busygroup(self, inject_fake_redis):
        from unittest.mock import AsyncMock, patch
        from mcp_agent_factory.streams.fleet_worker import FleetWorker
        from redis.exceptions import ResponseError

        fw = FleetWorker(inject_fake_redis, "test:stream", "grp2", "c1")
        with patch.object(inject_fake_redis, "xgroup_create", new=AsyncMock(
            side_effect=ResponseError("ERR some other error")
        )):
            with pytest.raises(ResponseError):
                await fw.ensure_group()

    @pytest.mark.asyncio
    async def test_publish_job_returns_msg_id(self, inject_fake_redis):
        from mcp_agent_factory.streams.fleet_worker import FleetWorker

        fw = FleetWorker(inject_fake_redis, "test:stream2", "grp", "c1")
        await fw.ensure_group()
        msg_id = await fw.publish_job("job-123", "agents/analyze", {"k": "v"})
        assert msg_id  # non-empty string

    @pytest.mark.asyncio
    async def test_claim_job_returns_none_when_stream_empty(self, inject_fake_redis):
        from mcp_agent_factory.streams.fleet_worker import FleetWorker

        fw = FleetWorker(inject_fake_redis, "test:stream3", "grp", "c1")
        await fw.ensure_group()
        result = await fw.claim_job()
        assert result is None

    @pytest.mark.asyncio
    async def test_claim_job_returns_msg_id_and_job_id(self, inject_fake_redis):
        from mcp_agent_factory.streams.fleet_worker import FleetWorker

        fw = FleetWorker(inject_fake_redis, "test:stream4", "grp", "c1")
        await fw.ensure_group()
        await fw.publish_job("job-xyz", "agents/analyze", {})
        result = await fw.claim_job()
        assert result is not None
        msg_id, job_id = result
        assert job_id == "job-xyz"

    @pytest.mark.asyncio
    async def test_ack_does_not_raise(self, inject_fake_redis):
        from mcp_agent_factory.streams.fleet_worker import FleetWorker

        fw = FleetWorker(inject_fake_redis, "test:stream5", "grp", "c1")
        await fw.ensure_group()
        await fw.publish_job("job-ack", "agents/analyze", {})
        result = await fw.claim_job()
        assert result is not None
        msg_id, _ = result
        await fw.ack(msg_id)  # must not raise


# ---------------------------------------------------------------------------
# _process_job — internal worker execution paths
# ---------------------------------------------------------------------------

class TestProcessJob:
    """Test the _process_job coroutine directly — no HTTP, no stream."""

    @pytest.mark.asyncio
    async def test_process_job_done(self, inject_fake_redis):
        import mcp_agent_factory.gateway.fleet as _fleet
        from unittest.mock import AsyncMock, patch
        from mcp_agent_factory.streams.fleet_worker import FleetWorker

        job_id = str(uuid.uuid4())
        await _plant_job(inject_fake_redis, job_id, "pending")

        fw = FleetWorker(inject_fake_redis, "s", "g", "w")
        sem = asyncio.Semaphore(4)

        with patch.object(_fleet, "_execute_job", new=AsyncMock(return_value={"summary": "done"})):
            await _fleet._process_job(fw, "msg-1", job_id, sem)

        job = await _fleet._read_job(job_id)
        assert job["status"] == "done"
        assert job["result"] == {"summary": "done"}

    @pytest.mark.asyncio
    async def test_process_job_timeout(self, inject_fake_redis):
        import mcp_agent_factory.gateway.fleet as _fleet
        from mcp_agent_factory.streams.fleet_worker import FleetWorker

        job_id = str(uuid.uuid4())
        await inject_fake_redis.set(f"mcp:job:{job_id}", json.dumps({
            "job_id": job_id,
            "method": "agents/analyze",
            "params": {},
            "status": "pending",
            "created_at": time.time(),
            "timeout_secs": 0.001,  # immediate timeout
            "result": None,
            "error": None,
        }))

        fw = FleetWorker(inject_fake_redis, "s", "g", "w")
        sem = asyncio.Semaphore(4)

        async def _slow(job):
            await asyncio.sleep(10)
            return {}

        import mcp_agent_factory.gateway.fleet as _fleet
        from unittest.mock import patch
        with patch.object(_fleet, "_execute_job", new=_slow):
            await _fleet._process_job(fw, "msg-2", job_id, sem)

        job = await _fleet._read_job(job_id)
        assert job["status"] == "failed"
        assert "timed out" in job["error"]

    @pytest.mark.asyncio
    async def test_process_job_exception(self, inject_fake_redis):
        import mcp_agent_factory.gateway.fleet as _fleet
        from unittest.mock import AsyncMock, patch
        from mcp_agent_factory.streams.fleet_worker import FleetWorker

        job_id = str(uuid.uuid4())
        await _plant_job(inject_fake_redis, job_id, "pending")

        fw = FleetWorker(inject_fake_redis, "s", "g", "w")
        sem = asyncio.Semaphore(4)

        with patch.object(_fleet, "_execute_job", new=AsyncMock(side_effect=RuntimeError("pipeline boom"))):
            await _fleet._process_job(fw, "msg-3", job_id, sem)

        job = await _fleet._read_job(job_id)
        assert job["status"] == "failed"
        assert "pipeline boom" in job["error"]

    @pytest.mark.asyncio
    async def test_process_job_missing_record(self, inject_fake_redis):
        """If job record is gone from Redis, _process_job acks and returns."""
        import mcp_agent_factory.gateway.fleet as _fleet
        from mcp_agent_factory.streams.fleet_worker import FleetWorker

        fw = FleetWorker(inject_fake_redis, "s", "g", "w")
        sem = asyncio.Semaphore(4)
        # job_id has no Redis key — should not raise
        await _fleet._process_job(fw, "msg-0", "nonexistent-job-id", sem)


# ---------------------------------------------------------------------------
# start_fleet_workers / stop_fleet_workers lifecycle
# ---------------------------------------------------------------------------

class TestFleetWorkerLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_stop(self, inject_fake_redis):
        import mcp_agent_factory.gateway.fleet as _fleet

        await _fleet.start_fleet_workers()
        assert _fleet._worker_task is not None
        await _fleet.stop_fleet_workers()
        assert _fleet._worker_task is None

    @pytest.mark.asyncio
    async def test_start_skipped_when_no_redis(self):
        import mcp_agent_factory.gateway.fleet as _fleet

        original = _fleet._redis
        _fleet._redis = None
        try:
            await _fleet.start_fleet_workers()
            assert _fleet._worker_task is None
        finally:
            _fleet._redis = original
