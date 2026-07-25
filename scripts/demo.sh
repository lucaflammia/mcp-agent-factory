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
# USAGE:
#   ./scripts/demo.sh [STEP]
#
# STEP (optional):
#   (empty)     Run all phases (0–6)
#   infra       Infrastructure seed (Kafka topics + Redis KV data)
#   0           Deterministic Orchestration validation
#   1           Privacy-First RAG (agents/analyze)
#   2           Jaeger trace observation
#   3           Provider switch (Gemini)
#   4           Orchestrator modes (pydantic_ai + langgraph)
#   5           CrewAI multi-agent scoping (Layer 3)
#   6           DSPy + GEPA optimization (Layer 4)
#   monitor     Grafana verification + traffic keeper
#
# OPTIONAL ENV VARS (client-side):
#   GATEWAY_URL   default: http://localhost:8000
#   PDF_PATH      default: data/samples/finance_q3_2024.pdf
#   QUERY         default: "Identify key KPIs and risk areas"
#
# Examples:
#   ./scripts/demo.sh               # All phases
#   ./scripts/demo.sh 1             # Phase 1 only
#   ./scripts/demo.sh infra         # Seed infrastructure
#   ./scripts/demo.sh 5             # CrewAI demo

set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
PDF_PATH="${PDF_PATH:-data/samples/finance_q3_2024.pdf}"
QUERY="${QUERY:-Identify key KPIs and risk areas}"
REQUESTED_STEP="${1:-}"  # Empty string = run all

# ── helpers ──────────────────────────────────────────────────────────────────

hr()  { printf '\n%s\n' "────────────────────────────────────────────────────"; }
hdr() { hr; printf '  %s\n' "$*"; hr; }

run_step() {
  # Returns 0 if REQUESTED_STEP matches this step (or is empty, meaning "run all")
  local step_name="$1"
  if [ -z "$REQUESTED_STEP" ]; then
    return 0  # empty = run all steps
  fi
  [ "$REQUESTED_STEP" = "$step_name" ]
}

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

# ── preflight (always runs) ───────────────────────────────────────────────────

require_cmd curl
require_cmd jq

check_health

# Only check monitoring for steps that need it (all steps except infra, 0, 5, 6)
if [ -z "$REQUESTED_STEP" ] || { [ "$REQUESTED_STEP" != "infra" ] && [ "$REQUESTED_STEP" != "0" ] && [ "$REQUESTED_STEP" != "5" ] && [ "$REQUESTED_STEP" != "6" ]; }; then
  check_monitoring
fi

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

if run_step "infra" || run_step ""; then
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
fi

# ── Phase 0: Deterministic Orchestration ─────────────────────────────────────

if run_step "0" || run_step ""; then
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
  echo "  ── Critic-Actor isolation ────────────────────────────────────────────"
  echo "  The evaluator (evaluator.py) runs as a stateless sandbox with no shared"
  echo "  context from the executing agent. It ingests the original constraints and"
  echo "  the final output, then runs a double-pass check:"
  echo "    1. Deterministic schema fulfillment validation"
  echo "    2. Isolated LLM call acting as a cynical QA auditor (0.0–1.0 score)"
  echo "  If the score is 0.0 (absolute failure) or a destructive tool is attempted,"
  echo "  the graph pauses via LangGraph interrupt() and persists state to Redis."
  echo "  Resume with: compiled.ainvoke(None, config)  [same thread_id]"
  echo "  Inspect paused state: http://localhost:8086 (Redis Commander)"
  echo ""
fi

# ── Phase 1: Privacy-First RAG ────────────────────────────────────────────────

if run_step "1" || run_step ""; then
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
fi

# ── Phase 2: Jaeger Trace ─────────────────────────────────────────────────────

if run_step "2" || run_step ""; then
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
fi

# ── Phase 3: Provider Switch ──────────────────────────────────────────────────

if run_step "3" || run_step ""; then
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
fi

# ── Phase 4: Orchestrator Modes ──────────────────────────────────────────────

if run_step "4" || run_step ""; then
  if [ -n "$REQUESTED_STEP" ] && [ "$REQUESTED_STEP" != "4" ]; then
    : # Don't print the hr and summary between 3 and 4 unless we're running all
  else
    hr
    echo "  Phases 0–3 complete."
    hr
  fi

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

  hdr "PHASE 4 — Orchestrator Modes (pydantic_ai + langgraph)"
  echo "  Three orchestration backends are available via the 'orchestrate' tool:"
  echo "    legacy      — regex-based ReAct loop (v0.1.0 default)"
  echo "    pydantic_ai — LLM structured outputs with Pydantic validation"
  echo "    langgraph   — state-machine with validate→plan→execute→evaluate→done"
  echo ""

  ORCH_TASK_PA="Echo the text: hello from pydantic_ai structured output"
  ORCH_TASK_LG="Add the numbers 17 and 25 using the add tool"

  echo "  ── pydantic_ai mode ──────────────────────────────────────────────────"
  echo "  Task: $ORCH_TASK_PA"
  echo ""
  ORCH_PA=$(mcp_call "tools/call" \
    "{\"name\":\"orchestrate\",\"arguments\":{\"task\":\"$ORCH_TASK_PA\",\"mode\":\"pydantic_ai\"}}" \
    || true)

  if echo "$ORCH_PA" | jq -e '.result.content[0]' >/dev/null 2>&1; then
    echo "$ORCH_PA" | jq -r '.result.content[0].text // (.result.content[0] | tostring)'
  elif echo "$ORCH_PA" | jq -e '.error' >/dev/null 2>&1; then
    echo "  ✗ pydantic_ai mode error:"
    echo "$ORCH_PA" | jq '.error'
  else
    echo "$ORCH_PA"
  fi

  echo ""
  echo "  ── langgraph mode ───────────────────────────────────────────────────"
  echo "  Task: $ORCH_TASK_LG"
  echo "  (State machine: validate → plan → execute → evaluate → done)"
  echo ""
  ORCH_LG=$(mcp_call "tools/call" \
    "{\"name\":\"orchestrate\",\"arguments\":{\"task\":\"$ORCH_TASK_LG\",\"mode\":\"langgraph\",\"thread_id\":\"demo-session-1\"}}" \
    || true)

  if echo "$ORCH_LG" | jq -e '.result.content[0]' >/dev/null 2>&1; then
    echo "$ORCH_LG" | jq -r '.result.content[0].text // (.result.content[0] | tostring)'
  elif echo "$ORCH_LG" | jq -e '.error' >/dev/null 2>&1; then
    echo "  ✗ langgraph mode error:"
    echo "$ORCH_LG" | jq '.error'
  else
    echo "$ORCH_LG"
  fi

  echo ""
  echo "  ── HITL interrupt behaviour ──────────────────────────────────────────"
  echo "  If the planner emits a step whose tool matches a destructive pattern"
  echo "  (write, delete, drop, deploy, ...), execute_node calls interrupt()"
  echo "  BEFORE running the tool. LangGraph serialises GraphState to Redis and"
  echo "  returns GraphInterrupt — the graph is paused in mid-flight."
  echo ""
  echo "  To resume after approval:"
  echo "    compiled.ainvoke(None, config)  # same thread_id"
  echo ""
  echo "  Inspect paused checkpoint:"
  echo "    Redis Commander → http://localhost:8086  (keys prefixed by thread_id)"
  echo "    Look for: require_user_approval=true, hitl_reason"
  echo ""
  echo "  evaluate_node also interrupts when the critic scores output 0.0"
  echo "  (absolute failure — autonomous retry would reproduce the same result)."
  echo ""
  echo "  Set ORCHESTRATOR_MODE=pydantic_ai or ORCHESTRATOR_MODE=langgraph in .env"
  echo "  to make a mode the default for all agents/analyze calls."
  echo ""
fi

# ── Phase 5: CrewAI Multi-Agent Scoping (Layer 3) ────────────────────────────

if run_step "5" || run_step ""; then
  hdr "PHASE 5 — CrewAI Multi-Agent Scoping (Layer 3)"
  echo "  MCPCrew coordinates independent ScopedAgents, each restricted to a"
  echo "  named subset of MCP tools.  Attempting a tool outside the allowed set"
  echo "  raises PermissionError — a hard security boundary enforced at call time."
  echo ""

  echo "  ── Tool Scoping (PermissionError enforcement) ─────────────────────────────"
  echo ""

  python3 - <<'PYEOF'
from mcp_agent_factory.crew import scope_tools, build_scoped_call_fn, ROLE_TOOL_PATTERNS

# ── Simulated full tool catalogue ─────────────────────────────────────────────
ALL_TOOLS = [
  {"name": "read_file"},
  {"name": "search_web"},
  {"name": "write_file"},
  {"name": "sql_query"},
  {"name": "embed_text"},
  {"name": "fetch_url"},
]

# ── Analyst role: read / search / fetch only ──────────────────────────────────
analyst_tools = scope_tools("analyst", ALL_TOOLS)
print(f"    analyst tools  ({len(analyst_tools)}/{len(ALL_TOOLS)}): "
  f"{[t['name'] for t in analyst_tools]}")

# ── Writer role: write / format only ─────────────────────────────────────────
writer_tools = scope_tools("writer", ALL_TOOLS)
print(f"    writer  tools  ({len(writer_tools)}/{len(ALL_TOOLS)}): "
  f"{[t['name'] for t in writer_tools]}")

# ── Orchestrator role: unrestricted ──────────────────────────────────────────
orch_tools = scope_tools("orchestrator", ALL_TOOLS)
print(f"    orchestrator   ({len(orch_tools)}/{len(ALL_TOOLS)}): all tools")

print("")

# ── PermissionError enforcement ───────────────────────────────────────────────
def base_call(tool_name, args):
  return f"called {tool_name}"

analyst_call = build_scoped_call_fn("analyst", analyst_tools, base_call)

# Allowed: read_file
result = analyst_call("read_file", {"path": "/data/report.pdf"})
print(f"    ✓ analyst → read_file:  {result}")

# Blocked: write_file
try:
  analyst_call("write_file", {"path": "/etc/passwd", "content": "hacked"})
  print("    ✗ write_file should have been blocked")
except PermissionError as exc:
  print(f"    ✓ analyst → write_file blocked (PermissionError)")
  print(f"      {str(exc)[:80]}")
PYEOF

  echo ""
  echo "  ── Live Crew Execution ────────────────────────────────────────────────────"
  echo ""

  python3 << 'PYEOF'
import sys
import os

# Suppress verbose debug output from CrewAI
os.environ["CREWAI_TRACING_ENABLED"] = "false"

try:
  from crewai import Agent as CrewAIAgent, Task as CrewAITask, Crew, Process, LLM

  print("    Executing: 'Summarise Q3 sales and draft the executive report'")
  print("")

  # Initialize Gemini LLM
  llm = LLM(model="gemini-2.5-flash", provider="google")

  # Create analyst agent
  analyst = CrewAIAgent(
    role="analyst",
    goal="Analyze Q3 sales data",
    backstory="You are a data analyst expert",
    llm=llm,
    verbose=False,
  )

  # Create writer agent
  writer = CrewAIAgent(
    role="writer",
    goal="Write executive reports",
    backstory="You are a business writer expert",
    llm=llm,
    verbose=False,
  )

  # Create tasks
  task1 = CrewAITask(
    description="Summarize Q3 sales data",
    expected_output="Key Q3 metrics and analysis",
    agent=analyst,
  )

  task2 = CrewAITask(
    description="Draft an executive report based on the Q3 analysis",
    expected_output="Executive summary in Markdown format",
    agent=writer,
  )

  # Create and run crew
  crew = Crew(
    agents=[analyst, writer],
    tasks=[task1, task2],
    process=Process.sequential,
    verbose=False,
  )

  result = crew.kickoff()

  # Display result (first 300 chars)
  output_str = str(result)
  preview = output_str[:300].replace('\n', '\n    ')
  print(f"    Result:\n    {preview}...")
  print("")

except ImportError:
  print("    ⚠ CrewAI not installed — install with: pip install 'mcp-agent-factory[crew]'")
  sys.exit(1)
except Exception as e:
  print(f"    ✗ Error: {type(e).__name__}: {e}")
  import traceback
  traceback.print_exc()
  sys.exit(1)
PYEOF

  echo ""
fi

# ── Phase 6: DSPy + GEPA Offline Prompt Optimization (Layer 4) ───────────────

if run_step "6" || run_step ""; then
  hdr "PHASE 6 — DSPy + GEPA Offline Prompt Optimization (Layer 4)"
  echo "  PromptOptimizer runs as an offline CI job — never in the request path."
  echo "  It ingests Kafka traces, compiles via DSPy BootstrapFewShot, mutates"
  echo "  via GEPA genetic evolution, then writes hot-reloadable JSON skill assets."
  echo ""

  python3 - <<'PYEOF'
import asyncio, tempfile, os
from pathlib import Path
from mcp_agent_factory.optimizer import PromptOptimizer, SkillCompiler

SKILLS_DIR = "/tmp/mcp_demo_skills"

async def run():
  optimizer = PromptOptimizer(
    kafka_topic="mcp-traces",
    skills_dir=SKILLS_DIR,
    dry_run=True,
  )

  # Dry-run: ingest with limit=0 returns empty corpus (no Kafka required)
  traces = await optimizer.ingest_traces(limit=0)
  print(f"  traces ingested (dry-run):  {len(traces)}")

  # compile() degrades gracefully when dspy/gepa are absent
  skills = await optimizer.compile(traces)
  print(f"  skills compiled:            {len(skills)}")

  # SkillCompiler writes JSON assets to disk
  compiler = SkillCompiler(output_dir=SKILLS_DIR)
  paths = compiler.compile_all(skills)
  print(f"  skill assets written:       {len(paths)}")

  # Show what was emitted
  skill_dir = Path(SKILLS_DIR)
  if skill_dir.exists():
    files = sorted(skill_dir.glob("*.json"))
    for f in files[:5]:
      print(f"    → {f.name}")
    if len(files) > 5:
      print(f"    … and {len(files) - 5} more")
  else:
    print("  (no assets emitted — attach Kafka + dspy for live optimization)")

asyncio.run(run())
PYEOF

  echo ""
  echo "  Install the optimizer backend for live DSPy + GEPA compilation:"
  echo "    pip install 'mcp-agent-factory[optimizer]'"
  echo ""
  echo "  Runtime hot-reload: send SIGHUP to the gateway process after writing"
  echo "  new skill JSON assets — no service restart required."
  echo ""
fi

# ── Enterprise Architecture Reference ────────────────────────────────────────

if run_step "monitor" || run_step ""; then
  hdr "ENTERPRISE ARCHITECTURE REFERENCE"
  echo "  Layer │ Pattern                     │ Where it runs                      │ What to observe"
  echo "  ────────────────────────────────────────────────────────────────────────────────────────────"
  echo "  L1    │ Structured I/O (PydanticAI) │ orchestrator.py / structured_agent  │ ValidationError on malformed LLM output"
  echo "  L2    │ Non-Determinism Gate        │ graph_orchestrator.py plan_node     │ ValidationError before any tool fires"
  echo "  L2    │ Critic-Actor (Trust+Verify) │ evaluator.py → evaluate_node        │ EvaluationResult.score + per-criterion log"
  echo "  L2    │ HITL Interrupt              │ execute_node / evaluate_node        │ GraphInterrupt; checkpoint in Redis :8086"
  echo "  L3    │ Multi-Agent Crew (CrewAI)   │ crew.py → MCPCrew.kickoff           │ PermissionError on out-of-scope tool call"
  echo "  L4    │ Offline Prompt Optimization │ optimizer.py → PromptOptimizer      │ JSON skill assets; SIGHUP reload"
  echo ""
  echo "  Infrastructure"
  echo "  ────────────────────────────────────────────────────────────────────────────────────────────"
  echo "  Apache Kafka  │ Async backpressure & trace stream for L4     │ http://localhost:8085"
  echo "  Redis         │ Distributed state, session store, HITL pause │ http://localhost:8086"
  echo "  MCP Inspector │ Decoupled, secure data & action layer        │ http://localhost:6274"
  echo ""
  echo "  Full rationale → README.md § Enterprise Production Patterns"
  echo ""
fi

# ── Background traffic keeper ─────────────────────────────────────────────────
# Keeps Jaeger Monitor and Prometheus rate() panels alive for 5 minutes by
# sending a lightweight health check every 15s. Without this, rate() windows
# drop to zero ~2 minutes after the demo ends and the UI tabs look empty.

if run_step "monitor" || run_step ""; then
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
fi
