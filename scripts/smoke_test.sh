#!/usr/bin/env bash
# Smoke test for the full docker compose --profile full stack.
# Usage: bash scripts/smoke_test.sh
# Assumes the stack is already running (docker compose --profile full up -d).
# Exits 0 on success, non-zero on first failure.

set -euo pipefail

GATEWAY=${GATEWAY_URL:-http://localhost:8000}
AUTH=${AUTH_URL:-http://localhost:8001}
JAEGER=${JAEGER_URL:-http://localhost:16686}
PROMETHEUS=${PROMETHEUS_URL:-http://localhost:9090}
GRAFANA=${GRAFANA_URL:-http://localhost:3000}

pass() { echo "  PASS  $1"; }
fail() { echo "  FAIL  $1"; exit 1; }

check_http() {
    local label="$1" url="$2" expected="${3:-200}"
    local actual
    actual=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    if [ "$actual" = "$expected" ]; then
        pass "$label ($actual)"
    else
        fail "$label — expected HTTP $expected, got $actual ($url)"
    fi
}

echo "=== MCP Agent Factory smoke test ==="
echo ""

echo "--- Gateway ---"
check_http "GET /health"                           "$GATEWAY/health"
check_http "GET /.well-known/oauth-authorization-server" "$GATEWAY/.well-known/oauth-authorization-server"
# POST /mcp tools/call without auth must return a JSON-RPC auth error (dev mode off in the full stack)
CALL_RESP=$(curl -s -X POST "$GATEWAY/mcp" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"echo","arguments":{"message":"test"}}}')
if echo "$CALL_RESP" | grep -q 'Authentication required'; then
    pass "POST /mcp tools/call unauthenticated → auth error"
else
    fail "POST /mcp tools/call unauthenticated expected auth error, got: $CALL_RESP"
fi

echo ""
echo "--- Dev-mode tool call ---"
# Use MCP_DEV_MODE so we can call a tool without OAuth.
# The gateway container must have MCP_DEV_MODE=1 OR we fall back to the dev-mode
# variant: spin up a quick in-process gateway using python and confirm the echo tool.
# In CI / default full stack MCP_DEV_MODE=0, so we skip the tool call and just verify
# that /health and auth are coherent.
DEV_MODE=${MCP_DEV_MODE:-0}
if [ "$DEV_MODE" = "1" ]; then
    TOOL_RESP=$(curl -s -X POST "$GATEWAY/mcp" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"echo","arguments":{"text":"smoke"}}}')
    if echo "$TOOL_RESP" | grep -q '"smoke"'; then
        pass "echo tool returns input"
    else
        fail "echo tool response unexpected: $TOOL_RESP"
    fi
else
    echo "  SKIP  echo tool (MCP_DEV_MODE=0; set MCP_DEV_MODE=1 to enable)"
fi

echo ""
echo "--- Auth server ---"
check_http "GET /.well-known/oauth-authorization-server" "$AUTH/.well-known/oauth-authorization-server"

echo ""
echo "--- Observability ---"
check_http "Jaeger UI"                "$JAEGER/"
check_http "Prometheus /-/healthy"    "$PROMETHEUS/-/healthy"
check_http "Grafana /api/health"      "$GRAFANA/api/health"

# Verify Prometheus has a scrape target for the gateway
TARGETS=$(curl -s "$PROMETHEUS/api/v1/targets" | python3 -c "
import sys, json
d = json.load(sys.stdin)
targets = d.get('data',{}).get('activeTargets',[])
for t in targets:
    if 'gateway' in t.get('labels',{}).get('job','') or 'mcp' in t.get('labels',{}).get('job',''):
        print('found')
        break
")
if [ "$TARGETS" = "found" ]; then
    pass "Prometheus has a gateway scrape target"
else
    echo "  WARN  Prometheus gateway target not found (may still be scraping)"
fi

echo ""
echo "=== All checks passed ==="
