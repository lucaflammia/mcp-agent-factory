#!/usr/bin/env bash
# demo.sh — "AI Agents at Work" live demo
#
# REQUIRED SETUP:
#   MCP_DEV_MODE=1 docker compose --profile full up -d
#
# MCP_DEV_MODE=1 must be set in the environment BEFORE starting the stack so
# the gateway process boots with auth bypass enabled. It cannot be changed
# without restarting the gateway container.
#
# OPTIONAL ENV VARS (client-side):
#   GATEWAY_URL   default: http://localhost:8000
#   PDF_PATH      default: data/samples/finance_q3_2024.pdf
#   QUERY         default: "Identify key KPIs and risk areas"
#
# Phase 1: Privacy-First RAG  — agents/analyze on the local PDF
# Phase 2: Jaeger trace link  — shows the full span chain
# Phase 3: Provider switch    — re-runs with provider=gemini (uses GEMINI_API_KEY if set)

set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
PDF_PATH="${PDF_PATH:-data/samples/finance_q3_2024.pdf}"
QUERY="${QUERY:-Identify key KPIs and risk areas}"

# ── helpers ──────────────────────────────────────────────────────────────────

hr()  { printf '\n%s\n' "────────────────────────────────────────────────────"; }
hdr() { hr; printf '  %s\n' "$*"; hr; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 is required but not installed."; exit 1; }
}

check_health() {
  local url="$GATEWAY_URL/health"
  local max_wait=30
  local waited=0
  printf 'Waiting for gateway at %s ' "$url"
  until curl -sf "$url" >/dev/null 2>&1; do
    if [ "$waited" -ge "$max_wait" ]; then
      echo ""
      echo "ERROR: Gateway not ready after ${max_wait}s. Run: MCP_DEV_MODE=1 docker compose --profile full up -d"
      exit 1
    fi
    printf '.'
    sleep 2
    waited=$((waited + 2))
  done
  echo " ready."
}

check_monitoring() {
  local prometheus_url="${PROMETHEUS_URL:-http://localhost:9090}"
  local jaeger_url="${JAEGER_URL:-http://localhost:16686}"

  printf 'Checking Prometheus at %s ' "$prometheus_url"
  if ! curl -sf "${prometheus_url}/-/healthy" >/dev/null 2>&1; then
    echo ""
    echo "ERROR: Prometheus is not reachable at ${prometheus_url}."
    echo ""
    echo "  Start the full observability stack with:"
    echo "    MCP_DEV_MODE=1 docker compose --profile full up -d"
    echo ""
    echo "  Or set PROMETHEUS_URL if it runs on a different host/port."
    exit 1
  fi
  echo " ready."

  printf 'Checking Jaeger at %s ' "$jaeger_url"
  if ! curl -sf "${jaeger_url}/api/services" >/dev/null 2>&1; then
    echo ""
    echo "ERROR: Jaeger is not reachable at ${jaeger_url}."
    echo ""
    echo "  Start the full observability stack with:"
    echo "    MCP_DEV_MODE=1 docker compose --profile full up -d"
    echo ""
    echo "  Or set JAEGER_URL if it runs on a different host/port."
    exit 1
  fi
  echo " ready."
}

mcp_call() {
  # mcp_call <method> <params_json> [extra_curl_opts...]
  local method="$1"
  local params="$2"
  shift 2
  curl -sf "$@" \
    -X POST "$GATEWAY_URL/mcp" \
    -H "Content-Type: application/json" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$method\",\"params\":$params}"
}

# ── preflight ─────────────────────────────────────────────────────────────────

require_cmd curl
require_cmd jq

check_health
check_monitoring

if [ ! -f "$PDF_PATH" ]; then
  echo "ERROR: PDF not found at '$PDF_PATH'. Set PDF_PATH to a valid path."
  exit 1
fi

# Gateway runs in Docker; ./data is mounted at /app/data inside the container.
# Strip the leading "data/" prefix and prepend the container mount point.
CONTAINER_PDF_PATH="/app/${PDF_PATH}"
PARAMS="{\"pdf_path\":\"$CONTAINER_PDF_PATH\",\"query\":\"$QUERY\"}"
PARAMS_GEMINI="{\"pdf_path\":\"$CONTAINER_PDF_PATH\",\"query\":\"$QUERY\",\"provider\":\"gemini\"}"

# Verify the gateway started with MCP_DEV_MODE=1 (auth bypass).
GATEWAY_CONTAINER=$(docker ps --filter "name=mcp-agent-factory-gateway" --format "{{.Names}}" 2>/dev/null | head -1)
if [ -n "$GATEWAY_CONTAINER" ]; then
  GW_DEV_MODE=$(docker exec "$GATEWAY_CONTAINER" sh -c 'echo $MCP_DEV_MODE' 2>/dev/null)
  if [ "$GW_DEV_MODE" != "1" ]; then
    echo "ERROR: Gateway is running without MCP_DEV_MODE=1 — auth is enforced."
    echo ""
    echo "  Restart the stack with:"
    echo "    MCP_DEV_MODE=1 docker compose --profile full up --build -d"
    echo ""
    exit 1
  fi
fi

# Check Ollama is reachable on the host.
if ! curl -sf "http://localhost:11434/" >/dev/null 2>&1; then
  echo "ERROR: Ollama is not running on localhost:11434."
  echo ""
  echo "  Start Ollama and pull the required model, then retry:"
  echo "    OLLAMA_HOST=0.0.0.0 ollama serve &"
  echo "    ollama pull llama3.2"
  echo ""
  echo "  Or set OLLAMA_MODEL to a model you have already pulled."
  exit 1
fi

# Check the required Ollama model is pulled.
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:0.6b-q4_K_M}"
if ! curl -sf "http://localhost:11434/api/tags" 2>/dev/null | grep -q "\"${OLLAMA_MODEL}"; then
  echo "ERROR: Ollama model \"${OLLAMA_MODEL}\" is not pulled."
  echo ""
  echo "  Pull it with:"
  echo "    ollama pull ${OLLAMA_MODEL}"
  echo ""
  echo "  Or set OLLAMA_MODEL to a model you already have (e.g. qwen3:0.6b-q4_K_M)."
  exit 1
fi

# Verify the gateway container can reach Ollama.
# On Linux, Ollama must bind to 0.0.0.0 (not just 127.0.0.1) for host.docker.internal to work.
if [ -n "$GATEWAY_CONTAINER" ]; then
  if ! docker exec "$GATEWAY_CONTAINER" wget -qO- "http://host.docker.internal:11434/" >/dev/null 2>&1; then
    echo "ERROR: Gateway container cannot reach Ollama at host.docker.internal:11434."
    echo ""
    echo "  On Linux, Ollama must listen on all interfaces, not just 127.0.0.1."
    echo "  Restart Ollama with:"
    echo "    OLLAMA_HOST=0.0.0.0 ollama serve"
    echo ""
    echo "  Then retry the demo."
    exit 1
  fi
fi

# ── Infrastructure seed: Kafka topics + Redis KV data ───────────────────────

hdr "INFRA SEED — Kafka topics + Redis KV store"

KAFKA_CONTAINER=$(docker ps --filter "name=mcp-agent-factory-kafka" --format "{{.Names}}" 2>/dev/null | head -1)
if [ -n "$KAFKA_CONTAINER" ]; then
  echo "  Creating Kafka topics (idempotent)..."
  for TOPIC in agents.analyze token.usage gateway.tool_calls; do
    docker exec "$KAFKA_CONTAINER" \
      kafka-topics --bootstrap-server localhost:9092 \
      --create --if-not-exists --topic "$TOPIC" \
      --partitions 3 --replication-factor 1 >/dev/null 2>&1 && \
      echo "    ✓ $TOPIC" || echo "    · $TOPIC (already exists)"
  done
  echo ""
  echo "  Kafka UI topics    → http://localhost:8085/ui/clusters/local/topics"
  echo "  Kafka UI consumers → http://localhost:8085/ui/clusters/local/consumer-groups"
  echo "  (consumer group 'mcp-demo-consumer' appears ~20s after first agents/analyze call)"
  echo ""
else
  echo "  ✗ Kafka container not found — skipping topic creation."
  echo ""
fi

echo "  Seeding Redis KV store with demo phrases..."
_kv_add() {
  local topic="$1"; local phrase="$2"
  curl -sf -X POST "$GATEWAY_URL/mcp" \
    -H "Content-Type: application/json" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"kv/add_phrase\",\"arguments\":{\"topic\":\"$topic\",\"phrase\":\"$phrase\"}}}" \
    >/dev/null 2>&1
}
_kv_add "finance" "EBITDA margin"
_kv_add "finance" "revenue growth"
_kv_add "finance" "operating cash flow"
_kv_add "risk"    "liquidity risk"
_kv_add "risk"    "market volatility"
echo "  ✓ 5 phrases seeded → Redis Commander http://localhost:8086/"
echo ""

# ── Phase 0: Deterministic Orchestration ─────────────────────────────────────

hdr "PHASE 0 — Deterministic Orchestration (ValidationGate on LLM output)"
echo "  v0.1.0 gateway validated incoming *client* requests (JSON-RPC shape, PII)."
echo "  v1.0.0 adds a second gate that validates what the *LLM* returns as a plan"
echo "  before any tool is allowed to execute."
echo ""
echo "  Valid plan → plan object; invalid plan → ValidationError (execution blocked)."
echo ""

python3 - <<'PYEOF'
from mcp_agent_factory.orchestrator import DeterministicOrchestrator
from pydantic import ValidationError

# ── CASE 1: valid LLM output passes the gate ─────────────────────────────────
valid_raw = {
  "intent": "extract KPIs from PDF",
  "steps": [
    {"tool_name": "pdf_extract", "arguments": {"path": "/app/data/report.pdf"}},
    {"tool_name": "summarize",   "arguments": {"style": "bullet"}},
  ],
}
try:
  plan = DeterministicOrchestrator.plan(valid_raw)
  print(f"  ✓ Valid plan accepted:  intent='{plan.intent}', steps={len(plan.steps)}")
except ValidationError as exc:
  print(f"  ✗ Unexpected rejection: {exc}")

# ── CASE 2: LLM omits 'intent' — execution is blocked ────────────────────────
malformed_raw = {
  "steps": [{"tool_name": "summarize", "arguments": {}}],
  # 'intent' missing — a real LLM hallucination
}
try:
  DeterministicOrchestrator.plan(malformed_raw)
  print("  ✗ Should have been rejected but wasn't")
except ValidationError as exc:
  fields = [e["loc"] for e in exc.errors()]
  print(f"  ✓ Malformed plan blocked: missing fields {fields}")

# ── CASE 3: duplicate adjacent steps — catches copy-paste LLM errors ──────────
duplicate_raw = {
  "intent": "echo twice",
  "steps": [
    {"tool_name": "echo", "arguments": {"message": "hi"}},
    {"tool_name": "echo", "arguments": {"message": "hi"}},  # exact duplicate
  ],
}
try:
  DeterministicOrchestrator.plan(duplicate_raw)
  print("  ✗ Duplicate steps should have been rejected")
except ValidationError as exc:
  print(f"  ✓ Duplicate adjacent step blocked: {exc.errors()[0]['msg']}")
PYEOF

echo ""

# ── Phase 1: Privacy-First RAG ────────────────────────────────────────────────

hdr "PHASE 1 — Privacy-First RAG (agents/analyze)"
echo "  PDF:   $PDF_PATH"
echo "  Query: $QUERY"
echo ""

# Seed Grafana panels by spreading calls across 2+ Prometheus scrape intervals.
# Prometheus scrapes every 15s; rate() needs counter increments at ≥2 distinct
# scrape points within the [1m] window. We run 4 calls spaced ~12s apart (~36s
# total) before the display call so all 5 panels have data by the time Phase 1
# output prints.
#
# Each agents/analyze call:
#   • increments mcp_auction_bids_total × 3 (analyst, summarizer, extractor)
#   • emits agent.pdf_extract / agent.prune / agent.pii_scrub / agent.llm_route spans
#     → OTel collector converts to traces_calls_total (Agent Pipeline, Pages Read,
#       Token Consumption panels)
echo "  Seeding Grafana metric panels (4 calls spread over ~36s)..."
for _i in 1 2 3 4; do
  printf "    call %d/4 … " "$_i"
  if mcp_call "agents/analyze" "$PARAMS" >/dev/null 2>&1; then
    echo "ok"
  else
    echo "warn: call failed (non-fatal)"
  fi
  [ "$_i" -lt 4 ] && sleep 12
done
echo ""
echo "  Waiting 20s for OTel BatchSpanProcessor flush + Prometheus scrape …"
sleep 20
echo ""

PHASE1=$(mcp_call "agents/analyze" "$PARAMS")

if echo "$PHASE1" | jq -e '.error' >/dev/null 2>&1; then
  ERROR_CODE=$(echo "$PHASE1" | jq -r '.error.code // empty')
  if [ "$ERROR_CODE" = "-32601" ]; then
    echo "ERROR: Method not found — the gateway image is stale."
    echo ""
    echo "  Rebuild and restart with:"
    echo "    MCP_DEV_MODE=1 docker compose --profile full up --build -d"
    echo ""
    echo "  (The agents/analyze handler was added after this image was built.)"
  elif [ "$ERROR_CODE" = "-32001" ]; then
    echo "ERROR: Authentication required — gateway started without MCP_DEV_MODE=1."
    echo ""
    echo "  Restart the stack with:"
    echo "    MCP_DEV_MODE=1 docker compose --profile full up --build -d"
    echo ""
  else
    echo "ERROR from gateway:"
    echo "$PHASE1" | jq '.error'
  fi
  exit 1
fi

echo "$PHASE1" | jq '{
  provider: .result.provider,
  pages_read: .result.pages_read,
  chunks_before: .result.chunks_before_pruning,
  chunks_after: .result.chunks_after_pruning,
  input_tokens: .result.input_tokens,
  output_tokens: .result.output_tokens,
  cost_usd: .result.cost_usd
}'
echo ""
echo "EXECUTIVE SUMMARY:"
echo "$PHASE1" | jq -r '.result.summary'

# ── Phase 2: Jaeger Trace ─────────────────────────────────────────────────────

hdr "PHASE 2 — Observe the Trace (Jaeger)"
echo "  Jaeger Search — click 'Find Traces' after opening this URL:"
echo "    http://localhost:16686/search?service=mcp-gateway&operation=mcp.agents%2Fanalyze&limit=20&lookback=1h"
echo ""
echo "  Jaeger Monitor (SPM — live call rate / latency per operation):"
echo "    http://localhost:16686/monitor"
echo "    → select 'mcp-gateway' from the service dropdown"
echo ""
echo "  Expected span chain:"
echo "    mcp.agents/analyze"
echo "      └─ agent.pdf_extract   [pages_read, chunk_count]"
echo "      └─ agent.prune         [input_tokens, output_tokens]"
echo "      └─ agent.pii_scrub     [input_tokens, output_tokens]"
echo "      └─ agent.llm_route     [provider, cost_usd]"

# ── Phase 3: Provider Switch ──────────────────────────────────────────────────

hdr "PHASE 3 — Live Provider Switch (Gemini)"

# Check whether the container has GEMINI_API_KEY.
# In MCP_DEV_MODE=1, a missing key is allowed — the gateway simulates Gemini
# via Ollama and still labels metrics as 'gemini' so Grafana panels show data.
if [ -n "$GATEWAY_CONTAINER" ]; then
  CONTAINER_GEMINI=$(docker exec "$GATEWAY_CONTAINER" sh -c 'echo $GEMINI_API_KEY' 2>/dev/null)
  if [ -z "$CONTAINER_GEMINI" ]; then
    echo "  ✗ GEMINI_API_KEY is not set — running in dev-mode simulation (Ollama backend, gemini label)."
    echo ""
    echo "  To use the real Gemini API, add your key and rebuild:"
    echo "    echo 'GEMINI_API_KEY=<your-key>' >> .env"
    echo "    MCP_DEV_MODE=1 docker compose --profile full up --build -d"
    echo ""
  fi
fi

# Seed Grafana Gemini panels with 4 calls spread over ~36s (same cadence as Phase 1).
echo "  Seeding Grafana Gemini panels (4 calls spread over ~36s)..."
for _i in 1 2 3 4; do
  printf "    call %d/4 … " "$_i"
  if mcp_call "agents/analyze" "$PARAMS_GEMINI" >/dev/null 2>&1; then
    echo "ok"
  else
    echo "warn: call failed (non-fatal)"
  fi
  [ "$_i" -lt 4 ] && sleep 12
done
echo ""
echo "  Waiting 20s for OTel BatchSpanProcessor flush + Prometheus scrape …"
sleep 20
echo ""

echo "  Requesting provider=gemini (display call)..."
echo ""

PHASE3=$(mcp_call "agents/analyze" "$PARAMS_GEMINI" || true)

if echo "$PHASE3" | jq -e '.error.code == -32602' >/dev/null 2>&1; then
  echo "Gateway response:"
  echo "$PHASE3" | jq '{code: .error.code, message: .error.message}'
  echo ""
  echo "  ✗ GEMINI_API_KEY not set — set it in your environment and rebuild to use Gemini."
elif echo "$PHASE3" | jq -e '.result' >/dev/null 2>&1; then
  PHASE3_CONTENT=$(echo "$PHASE3" | jq -r '.result.summary // empty')
  PHASE3_PROVIDER=$(echo "$PHASE3" | jq -r '.result.provider // "unknown"')
  PHASE3_COST=$(echo "$PHASE3" | jq -r '.result.cost_usd // 0')
  PHASE3_META=$(echo "$PHASE3" | jq '{provider: .result.provider, input_tokens: .result.input_tokens, output_tokens: .result.output_tokens, cost_usd: .result.cost_usd}' 2>/dev/null || true)
  echo "$PHASE3_META"
  echo ""
  echo "EXECUTIVE SUMMARY:"
  echo "$PHASE3_CONTENT"
  echo ""
  if echo "$PHASE3_PROVIDER" | grep -qi "gemini"; then
    echo "  ✓ Gemini responded successfully."
    if [ "$PHASE3_COST" = "0" ] || [ "$PHASE3_COST" = "0.0" ]; then
      echo "  ⚠ cost_usd=0 — gateway image may be stale. Rebuild: docker compose --profile full up --build -d"
    fi
  else
    echo "  ✗ Gemini fell back to Ollama (provider=$PHASE3_PROVIDER)."
    echo "    Check gateway logs: docker logs \$(docker ps -qf name=gateway) 2>&1 | grep -i gemini"
  fi
else
  echo "Gateway response:"
  echo "$PHASE3"
fi

hr
echo "  Demo complete."
hr

# ── Grafana verification ───────────────────────────────────────────────────────

PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"

echo ""
echo "  Verifying Grafana panel metrics in Prometheus …"
echo ""

_prom_check() {
  local label="$1"
  local query="$2"
  local result
  result=$(curl -sf "${PROMETHEUS_URL}/api/v1/query" \
    --data-urlencode "query=${query}" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); v=d.get('data',{}).get('result',[]); print('ok' if v else 'no-data')" 2>/dev/null || echo "unreachable")
  printf "    %-35s %s\n" "$label" "$result"
}

_prom_check "Auction Bids" \
  "sum(mcp_auction_bids_total{job=\"mcp-gateway\"})"

_prom_check "Agent Pipeline (calls rate)" \
  "sum(rate(traces_calls_total{span_name=~\"agent[.].*\"}[5m]))"

_prom_check "Token Consumption (cumulative)" \
  "sum(mcp_agent_input_tokens_total) by (provider)"

_prom_check "Cost by Provider (cumulative)" \
  "sum(mcp_agent_cost_usd_total) by (provider)"

_prom_check "Gemini cost recorded" \
  "mcp_agent_cost_usd_total{provider=\"gemini\"}"

echo ""
echo "  Grafana dashboard (refreshes every 10s):"
echo "    http://localhost:3000/d/mcp-overview/mcp-agent-factory-e28094-overview?orgId=1&refresh=10s"
echo ""
echo "  If any check shows 'no-data', wait 30s and refresh Grafana — Prometheus"
echo "  may still be in its next scrape interval."
echo ""

echo "  Prometheus query shortcuts (paste into http://localhost:9090/graph):"
echo "    Call rate:    rate(traces_calls_total{service_name=\"mcp-gateway\"}[1m])"
echo "    Token cost:   sum(mcp_agent_cost_usd_total) by (provider)"
echo "    Latency p99:  histogram_quantile(0.99, sum(rate(traces_duration_milliseconds_bucket{service_name=\"mcp-gateway\"}[1m])) by (le))"
echo ""

# ── Background traffic keeper ─────────────────────────────────────────────────
# Keeps Jaeger Monitor and Prometheus rate() panels alive for 5 minutes by
# sending a lightweight health check every 15s. Without this, rate() windows
# drop to zero ~2 minutes after the demo ends and the UI tabs look empty.
hdr "TRAFFIC KEEPER — keeping metrics alive for 5 minutes"
echo "  Sending a /health ping every 15s so Jaeger Monitor + Prometheus rate()"
echo "  panels stay populated while you explore the UIs."
echo "  Press Ctrl-C to stop early."
echo ""

_KEEPER_END=$(( $(date +%s) + 300 ))
_KEEPER_N=0
while [ "$(date +%s)" -lt "$_KEEPER_END" ]; do
  _KEEPER_N=$((_KEEPER_N + 1))
  _remaining=$(( _KEEPER_END - $(date +%s) ))
  printf "  ping %2d — %ds remaining  " "$_KEEPER_N" "$_remaining"
  if curl -sf "${GATEWAY_URL}/health" >/dev/null 2>&1; then
    echo "ok"
  else
    echo "warn: gateway unreachable"
  fi
  sleep 15
done
echo ""
echo "  Traffic keeper done. All UI panels show 5 min of activity."
echo ""
