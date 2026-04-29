"""
M011/S02 integration tests — OpenTelemetry end-to-end trace verification.

Requires a running full stack (docker compose --profile full up) with
MCP_DEV_MODE=1 on the gateway.

Run with:
    pytest tests/test_m011_otel_integration.py -m integration -v
"""
from __future__ import annotations

import time

import httpx
import pytest

GATEWAY_URL = "http://localhost:8000"
JAEGER_URL = "http://localhost:16686"


def _jaeger_traces(service: str = "mcp-gateway", limit: int = 20) -> list[dict]:
    resp = httpx.get(f"{JAEGER_URL}/api/traces", params={"service": service, "limit": limit}, timeout=5)
    resp.raise_for_status()
    return resp.json().get("data", [])


def _send_mcp(method: str, params: dict) -> dict:
    resp = httpx.post(
        f"{GATEWAY_URL}/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


@pytest.mark.integration
class TestOtelTraces:
    def test_gateway_registered_in_jaeger(self):
        """mcp-gateway service must appear in Jaeger after any request."""
        resp = httpx.get(f"{JAEGER_URL}/api/services", timeout=5)
        assert resp.status_code == 200
        services = resp.json().get("data", [])
        assert "mcp-gateway" in services, f"Expected mcp-gateway in {services}"

    def test_echo_produces_mcp_span(self):
        """echo tool call must produce a mcp.tools/call span in Jaeger."""
        marker = f"otel-test-{int(time.time())}"
        result = _send_mcp("tools/call", {"name": "echo", "arguments": {"text": marker}})
        assert result.get("result", {}).get("content", [{}])[0].get("text") == marker

        # Give BatchSpanProcessor time to flush
        deadline = time.time() + 10
        found = False
        while time.time() < deadline:
            traces = _jaeger_traces()
            for trace in traces:
                for span in trace.get("spans", []):
                    if span["operationName"] == "mcp.tools/call":
                        attrs = {t["key"]: t["value"] for t in span.get("tags", [])}
                        if attrs.get("mcp.tool") == "echo":
                            found = True
                            break
                if found:
                    break
            if found:
                break
            time.sleep(1)

        assert found, "mcp.tools/call span for echo not found in Jaeger within 10s"

    def test_add_produces_tool_child_span(self):
        """add tool call must produce a mcp.tools/call → tool.add parent-child chain."""
        _send_mcp("tools/call", {"name": "add", "arguments": {"a": 10, "b": 5}})

        deadline = time.time() + 10
        found_root = False
        found_child = False
        while time.time() < deadline:
            traces = _jaeger_traces()
            for trace in traces:
                spans = trace.get("spans", [])
                span_by_id = {s["spanID"]: s for s in spans}
                for span in spans:
                    if span["operationName"] == "tool.add":
                        found_child = True
                        # Verify parent is the mcp.tools/call span
                        refs = span.get("references", [])
                        if refs:
                            parent = span_by_id.get(refs[0]["spanID"], {})
                            if parent.get("operationName") == "mcp.tools/call":
                                found_root = True
            if found_root and found_child:
                break
            time.sleep(1)

        assert found_child, "tool.add child span not found in Jaeger"
        assert found_root, "tool.add span not parented under mcp.tools/call"
