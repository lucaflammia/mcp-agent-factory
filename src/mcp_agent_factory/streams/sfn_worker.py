"""
AWS Lambda handler for the Step Functions fleet worker.

Step Functions invokes this handler for each fleet job. The handler runs the
existing 4-layer pipeline (via the gateway's HTTP endpoint) and returns the
result dict. Step Functions captures the return value as the execution output
and uses the Retry/Catch configuration in the state machine for durability.

Environment variables
---------------------
GATEWAY_URL   Base URL of the gateway (e.g. https://api.example.com or
              http://localhost:8000 for local development). The handler calls
              POST /mcp and unwraps the JSON-RPC response.
JWT_SECRET    Shared secret used to sign a service-to-service token so the
              gateway does not reject the internal call with 401. When
              MCP_DEV_MODE=1 (local dev) the JWT is not required.
MCP_DEV_MODE  Set to 1 to skip JWT signing (local development only).

The handler raises an exception on failure so Step Functions can apply the
Retry policy defined in the state machine definition and transition to the
MarkFailed Catch state after all retries are exhausted.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GATEWAY_URL: str = os.getenv("GATEWAY_URL", "http://localhost:8000")
MCP_DEV_MODE: bool = os.getenv("MCP_DEV_MODE", "0") == "1"


def _make_token() -> str | None:
    """Sign a minimal service-account JWT for gateway auth."""
    if MCP_DEV_MODE:
        return None
    secret = os.getenv("JWT_SECRET")
    if not secret:
        return None
    try:
        import time

        import jwt as _jwt  # type: ignore[import]

        payload = {
            "sub": "sfn-worker",
            "scope": "tools:call tools:orchestrate",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        }
        return _jwt.encode(payload, secret, algorithm="HS256")
    except Exception as exc:
        logger.warning("sfn_worker: JWT signing failed: %s", exc)
        return None


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point.

    ``event`` is the parsed JSON that was passed as the input to
    ``sfn.start_execution``. It is the same job dict that the gateway wrote to
    Redis when the job was submitted.

    Returns the result dict on success, or raises an exception so Step
    Functions can apply the configured Retry policy.
    """
    job_id: str = event.get("job_id", "unknown")
    method: str = event.get("method", "")
    params: dict[str, Any] = event.get("params", {})

    logger.info('{"event":"sfn_worker_start","job_id":"%s","method":"%s"}', job_id, method)

    payload = {
        "jsonrpc": "2.0",
        "id": job_id,
        "method": method,
        "params": params,
    }

    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = _make_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(timeout=float(event.get("timeout_secs", 300))) as client:
            resp = client.post(f"{GATEWAY_URL}/mcp", json=payload, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Gateway HTTP {exc.response.status_code}: {exc.response.text}") from exc
    except Exception as exc:
        raise RuntimeError(f"Gateway call failed: {exc}") from exc

    body = resp.json()
    if "error" in body:
        err = body["error"]
        raise RuntimeError(err.get("message", str(err)))

    result: dict[str, Any] = body.get("result", {})
    logger.info('{"event":"sfn_worker_done","job_id":"%s"}', job_id)
    return result
