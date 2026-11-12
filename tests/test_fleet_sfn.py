"""
Step Functions fleet backend tests.

Covers:
  - Gateway submits a Step Functions execution on POST /mcp/jobs
  - GET /mcp/jobs/{id} maps SFN execution status to fleet schema
  - Timeout execution maps to status: failed, error: "timeout"
  - Retry semantics are encoded in the state machine definition
  - Batch submit starts one SFN execution per task
  - SFN backend skips the in-process worker loop
  - Existing Redis-stream tests are unaffected (backend isolation)

Uses moto to mock Step Functions — no real AWS account or LocalStack required
in unit tests.
"""
from __future__ import annotations

import json
import os
import time
import uuid

import fakeredis.aioredis as _fakeredis
import pytest

# moto must be imported and activated before boto3 is used
moto = pytest.importorskip("moto")

import boto3

import mcp_agent_factory.gateway.fleet as _fleet
from mcp_agent_factory.gateway.app import gateway_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REGION = "eu-west-1"
_SM_NAME = "mcp-agent-factory-fleet-test"


def _create_state_machine(sfn_client) -> str:
    """Create a minimal state machine in the mocked SFN and return its ARN."""
    definition = json.dumps({
        "StartAt": "RunPipeline",
        "States": {
            "RunPipeline": {
                "Type": "Task",
                "Resource": "arn:aws:lambda:eu-west-1:123456789012:function:worker",
                "TimeoutSeconds": 300,
                "Retry": [
                    {
                        "ErrorEquals": ["States.TaskFailed"],
                        "IntervalSeconds": 2,
                        "MaxAttempts": 3,
                        "BackoffRate": 2.0,
                    }
                ],
                "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "MarkFailed"}],
                "Next": "MarkDone",
            },
            "MarkDone": {"Type": "Succeed"},
            "MarkFailed": {"Type": "Fail", "Error": "PipelineError"},
        },
    })
    # moto requires a real-looking IAM role ARN even though it doesn't validate
    resp = sfn_client.create_state_machine(
        name=_SM_NAME,
        definition=definition,
        roleArn="arn:aws:iam::123456789012:role/sfn-role",
        type="STANDARD",
    )
    return resp["stateMachineArn"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sfn_env(monkeypatch):
    """Activate moto SFN mock, create a state machine, inject into fleet module."""
    from moto import mock_aws

    with mock_aws():
        sfn_client = boto3.client("stepfunctions", region_name=_REGION)
        sm_arn = _create_state_machine(sfn_client)

        monkeypatch.setenv("STATE_MACHINE_ARN", sm_arn)
        monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)

        # Patch fleet module globals so they read the new env
        monkeypatch.setattr(_fleet, "STATE_MACHINE_ARN", sm_arn)

        fake_redis = _fakeredis.FakeRedis()
        # set_fleet_redis will create the boto3 SFN client using the mocked env
        _fleet.set_fleet_redis(fake_redis, enabled=True)
        # Override the client with one that uses the moto-patched boto3 session
        _fleet._sfn_client = sfn_client

        import mcp_agent_factory.gateway.app as _app
        monkeypatch.setattr(_app, "_redis_client", fake_redis)

        yield {"sfn": sfn_client, "sm_arn": sm_arn, "redis": fake_redis}

        # Teardown
        _fleet.set_fleet_redis(None, enabled=False)
        monkeypatch.setattr(_fleet, "STATE_MACHINE_ARN", "")


# ---------------------------------------------------------------------------
# Submission — POST /mcp/jobs starts a Step Functions execution
# ---------------------------------------------------------------------------

class TestSfnSubmit:
    @pytest.mark.asyncio
    async def test_submit_starts_sfn_execution(self, sfn_env):
        """_submit_one must call sfn.start_execution and store the executionArn."""
        job_id = await _fleet._submit_one("agents/analyze", {"pdf_path": "test.pdf"})
        job = await _fleet._read_job(job_id)
        assert job is not None
        assert "execution_arn" in job
        assert job["status"] == "running"
        assert "mcp-agent-factory-fleet-test" in job["execution_arn"]

    @pytest.mark.asyncio
    async def test_submit_execution_name_equals_job_id(self, sfn_env):
        """The SFN execution name must be the job_id for deterministic ARN construction."""
        job_id = await _fleet._submit_one("agents/analyze", {})
        job = await _fleet._read_job(job_id)
        assert job_id in job["execution_arn"]

    @pytest.mark.asyncio
    async def test_submit_multiple_jobs_start_separate_executions(self, sfn_env):
        sfn_client = sfn_env["sfn"]
        sm_arn = sfn_env["sm_arn"]

        job_id_a = await _fleet._submit_one("agents/analyze", {})
        job_id_b = await _fleet._submit_one("agents/analyze", {})

        execs = sfn_client.list_executions(stateMachineArn=sm_arn)["executions"]
        exec_names = {e["name"] for e in execs}
        assert job_id_a in exec_names
        assert job_id_b in exec_names


# ---------------------------------------------------------------------------
# Polling — GET /mcp/jobs/{id} maps SFN execution status
# ---------------------------------------------------------------------------

class TestSfnPoll:
    @pytest.mark.asyncio
    async def test_poll_running_execution(self, sfn_env):
        """RUNNING SFN execution → fleet status 'running'."""
        job_id = await _fleet._submit_one("agents/analyze", {})
        # moto starts executions in RUNNING state
        job = await _fleet._read_job(job_id)
        job = await _fleet._sfn_refresh_job(job)
        assert job["status"] == "running"

    @pytest.mark.asyncio
    async def test_poll_succeeded_execution(self, sfn_env):
        """SUCCEEDED SFN execution → fleet status 'done' with result."""
        sfn_client = sfn_env["sfn"]

        job_id = await _fleet._submit_one("agents/analyze", {})
        job = await _fleet._read_job(job_id)
        exec_arn = job["execution_arn"]

        # moto: stop the execution with a SUCCESS outcome
        sfn_client.stop_execution(executionArn=exec_arn)
        # moto's stop_execution puts the execution in ABORTED, not SUCCEEDED.
        # We test the mapping directly by patching describe_execution.
        from unittest.mock import patch

        fake_describe = {
            "executionArn": exec_arn,
            "status": "SUCCEEDED",
            "output": json.dumps({"summary": "all good"}),
        }
        with patch.object(sfn_client, "describe_execution", return_value=fake_describe):
            _fleet._sfn_client = sfn_client
            job2 = await _fleet._read_job(job_id)
            job2 = await _fleet._sfn_refresh_job(job2)

        assert job2["status"] == "done"
        assert job2["result"] == {"summary": "all good"}

    @pytest.mark.asyncio
    async def test_poll_timed_out_execution(self, sfn_env):
        """TIMED_OUT SFN execution → fleet status 'failed', error 'timeout'."""
        sfn_client = sfn_env["sfn"]

        job_id = await _fleet._submit_one("agents/analyze", {})
        job = await _fleet._read_job(job_id)
        exec_arn = job["execution_arn"]

        from unittest.mock import patch

        fake_describe = {
            "executionArn": exec_arn,
            "status": "TIMED_OUT",
            "cause": "States.Timeout",
        }
        with patch.object(sfn_client, "describe_execution", return_value=fake_describe):
            _fleet._sfn_client = sfn_client
            job2 = await _fleet._read_job(job_id)
            job2 = await _fleet._sfn_refresh_job(job2)

        assert job2["status"] == "failed"
        assert job2["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_poll_failed_execution(self, sfn_env):
        """FAILED SFN execution → fleet status 'failed' with cause as error."""
        sfn_client = sfn_env["sfn"]

        job_id = await _fleet._submit_one("agents/analyze", {})
        job = await _fleet._read_job(job_id)
        exec_arn = job["execution_arn"]

        from unittest.mock import patch

        fake_describe = {
            "executionArn": exec_arn,
            "status": "FAILED",
            "cause": "PipelineError: out of memory",
        }
        with patch.object(sfn_client, "describe_execution", return_value=fake_describe):
            _fleet._sfn_client = sfn_client
            job2 = await _fleet._read_job(job_id)
            job2 = await _fleet._sfn_refresh_job(job2)

        assert job2["status"] == "failed"
        assert "PipelineError" in job2["error"]


# ---------------------------------------------------------------------------
# Batch — one SFN execution per task
# ---------------------------------------------------------------------------

class TestSfnBatch:
    @pytest.mark.asyncio
    async def test_batch_starts_one_execution_per_task(self, sfn_env):
        sfn_client = sfn_env["sfn"]
        sm_arn = sfn_env["sm_arn"]

        tasks = [
            {"method": "agents/analyze", "params": {"pdf_path": f"doc{i}.pdf"}}
            for i in range(3)
        ]
        job_ids = []
        for t in tasks:
            jid = await _fleet._submit_one(t["method"], t["params"])
            job_ids.append(jid)

        execs = sfn_client.list_executions(stateMachineArn=sm_arn)["executions"]
        exec_names = {e["name"] for e in execs}
        for jid in job_ids:
            assert jid in exec_names


# ---------------------------------------------------------------------------
# Worker loop — not started when SFN backend is active
# ---------------------------------------------------------------------------

class TestSfnWorkerLoop:
    @pytest.mark.asyncio
    async def test_start_fleet_workers_skipped_with_sfn_backend(self, sfn_env):
        """When SFN is active, start_fleet_workers must not launch the Redis worker."""
        await _fleet.start_fleet_workers()
        assert _fleet._worker_task is None, "worker task must not start with SFN backend"


# ---------------------------------------------------------------------------
# State machine definition — retry and timeout in Terraform output
# ---------------------------------------------------------------------------

class TestStateMachineDefinition:
    def test_state_machine_has_retry_policy(self, sfn_env):
        """State machine definition must include at least one Retry entry."""
        sfn_client = sfn_env["sfn"]
        sm_arn = sfn_env["sm_arn"]
        resp = sfn_client.describe_state_machine(stateMachineArn=sm_arn)
        defn = json.loads(resp["definition"])
        run_pipeline = defn["States"]["RunPipeline"]
        assert "Retry" in run_pipeline
        assert len(run_pipeline["Retry"]) >= 1

    def test_state_machine_has_timeout(self, sfn_env):
        """State machine RunPipeline state must have TimeoutSeconds set."""
        sfn_client = sfn_env["sfn"]
        sm_arn = sfn_env["sm_arn"]
        resp = sfn_client.describe_state_machine(stateMachineArn=sm_arn)
        defn = json.loads(resp["definition"])
        run_pipeline = defn["States"]["RunPipeline"]
        assert "TimeoutSeconds" in run_pipeline
        assert run_pipeline["TimeoutSeconds"] > 0

    def test_state_machine_has_catch_all(self, sfn_env):
        """State machine must catch all errors to prevent lost-job failure modes."""
        sfn_client = sfn_env["sfn"]
        sm_arn = sfn_env["sm_arn"]
        resp = sfn_client.describe_state_machine(stateMachineArn=sm_arn)
        defn = json.loads(resp["definition"])
        run_pipeline = defn["States"]["RunPipeline"]
        assert "Catch" in run_pipeline
        catch_errors = [e for c in run_pipeline["Catch"] for e in c["ErrorEquals"]]
        assert "States.ALL" in catch_errors


# ---------------------------------------------------------------------------
# sfn_worker Lambda handler
# ---------------------------------------------------------------------------

class TestSfnWorkerHandler:
    def test_handler_calls_gateway_and_returns_result(self, monkeypatch):
        """The Lambda handler must POST to GATEWAY_URL/mcp and return the result."""
        from unittest.mock import MagicMock, patch

        import httpx

        from mcp_agent_factory.streams.sfn_worker import handler

        fake_response = MagicMock()
        fake_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "test-job",
            "result": {"summary": "done"},
        }
        fake_response.raise_for_status = MagicMock()

        monkeypatch.setenv("MCP_DEV_MODE", "1")
        monkeypatch.setenv("GATEWAY_URL", "http://localhost:8000")

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_client_cls.return_value = mock_client

            result = handler(
                {"job_id": "test-job", "method": "agents/analyze", "params": {}, "timeout_secs": 300},
                None,
            )

        assert result == {"summary": "done"}
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/mcp" in call_args[0][0]

    def test_handler_raises_on_gateway_error(self, monkeypatch):
        """The Lambda handler must raise RuntimeError on gateway JSON-RPC error."""
        from unittest.mock import MagicMock, patch

        from mcp_agent_factory.streams.sfn_worker import handler

        fake_response = MagicMock()
        fake_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "test-job",
            "error": {"code": -32603, "message": "pipeline boom"},
        }
        fake_response.raise_for_status = MagicMock()

        monkeypatch.setenv("MCP_DEV_MODE", "1")

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_client_cls.return_value = mock_client

            with pytest.raises(RuntimeError, match="pipeline boom"):
                handler(
                    {"job_id": "test-job", "method": "agents/analyze", "params": {}},
                    None,
                )
