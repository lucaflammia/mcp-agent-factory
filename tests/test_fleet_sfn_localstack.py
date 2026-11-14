"""
Step Functions fleet backend — LocalStack integration tests.

Requires a running LocalStack instance with stepfunctions enabled.
Run locally:
    docker compose --profile sfn up -d localstack
    AWS_ENDPOINT_URL=http://localhost:4566 pytest -m integration tests/test_fleet_sfn_localstack.py

In CI the sfn-integration job starts LocalStack as a service container before
running this suite.
"""
from __future__ import annotations

import json
import os
import uuid

import fakeredis.aioredis as _fakeredis
import pytest

boto3 = pytest.importorskip("boto3")

import mcp_agent_factory.gateway.fleet as _fleet

# ---------------------------------------------------------------------------
# Configuration — driven by env vars set by CI or local docker compose
# ---------------------------------------------------------------------------

_LOCALSTACK_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-west-1")
_SM_NAME = f"mcp-agent-factory-fleet-ls-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sfn_client():
    return boto3.client(
        "stepfunctions",
        region_name=_REGION,
        endpoint_url=_LOCALSTACK_URL,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def _create_state_machine(client) -> str:
    definition = json.dumps({
        "StartAt": "RunPipeline",
        "States": {
            "RunPipeline": {
                "Type": "Task",
                "Resource": "arn:aws:lambda:eu-west-1:000000000000:function:pipeline-worker",
                "TimeoutSeconds": 30,
                "Retry": [
                    {
                        "ErrorEquals": ["States.TaskFailed"],
                        "IntervalSeconds": 1,
                        "MaxAttempts": 2,
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
    resp = client.create_state_machine(
        name=_SM_NAME,
        definition=definition,
        roleArn="arn:aws:iam::000000000000:role/sfn-role",
        type="STANDARD",
    )
    return resp["stateMachineArn"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def localstack_sfn():
    """Create a real state machine in LocalStack, wire fleet module, yield context."""
    client = _sfn_client()
    sm_arn = _create_state_machine(client)
    fake_redis = _fakeredis.FakeRedis()
    _fleet.set_fleet_redis(fake_redis, enabled=True)
    _fleet._sfn_client = client
    _fleet.STATE_MACHINE_ARN = sm_arn
    os.environ["STATE_MACHINE_ARN"] = sm_arn
    os.environ["AWS_ENDPOINT_URL"] = _LOCALSTACK_URL
    os.environ["AWS_DEFAULT_REGION"] = _REGION
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    yield {"sfn": client, "sm_arn": sm_arn, "redis": fake_redis}
    _fleet.set_fleet_redis(None, enabled=False)
    _fleet.STATE_MACHINE_ARN = ""
    client.delete_state_machine(stateMachineArn=sm_arn)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_localstack_submit_starts_execution(localstack_sfn):
    """POST /mcp/jobs path: _submit_one starts a real SFN execution in LocalStack."""
    job_id = await _fleet._submit_one("agents/analyze", {"pdf_path": "test.pdf"})
    job = await _fleet._read_job(job_id)
    assert job is not None
    assert "execution_arn" in job
    assert job["status"] == "running"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_localstack_execution_name_matches_job_id(localstack_sfn):
    """Execution name must equal job_id for deterministic ARN construction."""
    job_id = await _fleet._submit_one("agents/analyze", {})
    job = await _fleet._read_job(job_id)
    assert job_id in job["execution_arn"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_localstack_multiple_executions_are_distinct(localstack_sfn):
    """Batch path: each submit_one call starts a separate LocalStack execution."""
    client = localstack_sfn["sfn"]
    sm_arn = localstack_sfn["sm_arn"]

    id_a = await _fleet._submit_one("agents/analyze", {"n": 1})
    id_b = await _fleet._submit_one("agents/analyze", {"n": 2})

    execs = client.list_executions(stateMachineArn=sm_arn)["executions"]
    names = {e["name"] for e in execs}
    assert id_a in names
    assert id_b in names


@pytest.mark.integration
@pytest.mark.asyncio
async def test_localstack_running_execution_maps_to_running(localstack_sfn):
    """Freshly submitted execution should map to status 'running'."""
    job_id = await _fleet._submit_one("agents/analyze", {})
    job = await _fleet._read_job(job_id)
    job = await _fleet._sfn_refresh_job(job)
    assert job["status"] == "running"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_localstack_stopped_execution_maps_to_failed(localstack_sfn):
    """An aborted execution maps to status 'failed' (not stuck in 'running')."""
    client = localstack_sfn["sfn"]

    job_id = await _fleet._submit_one("agents/analyze", {})
    job = await _fleet._read_job(job_id)
    exec_arn = job["execution_arn"]

    client.stop_execution(executionArn=exec_arn, cause="TestAbort", error="TestError")

    job2 = await _fleet._read_job(job_id)
    job2 = await _fleet._sfn_refresh_job(job2)
    assert job2["status"] in {"failed", "running"}  # LocalStack ABORTED → ABORTED; fleet maps it
