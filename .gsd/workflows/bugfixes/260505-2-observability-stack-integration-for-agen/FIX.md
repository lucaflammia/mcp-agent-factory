# Fix: Observability Stack Integration

## Root Causes

### 1. Span attribute names missing `agent.` prefix (`analyst.py`)
The dashboard queries `traces_calls_total` with label filters like `agent_provider`, `agent_pages_read`, etc. The OTel Collector's `spanmetrics` processor maps span attribute `agent.provider` → Prometheus label `agent_provider`. The analyst code was setting plain attribute names without the prefix, so all dimension labels were empty and the panels showed no data.

**Fix:** Added `agent.` prefix to all span attributes in `src/mcp_agent_factory/agents/analyst.py`:
- `agent.pages_read`, `agent.total_pages`, `agent.chunk_count` on `agent.pdf_extract` span
- `agent.provider`, `agent.input_tokens`, `agent.output_tokens`, `agent.cost_usd` on `agent.llm_route` span

### 2. Dashboard metric names wrong (`mcp-overview.json`)
The Prometheus exporter under namespace `traces` exports `traces_calls_total` and `traces_duration_milliseconds_bucket`. The dashboard was querying `traces_spanmetrics_calls_total` and `traces_spanmetrics_duration_milliseconds_bucket` (incorrect prefix).

**Fix:** Updated all 6 agent-pipeline panel queries in `observability/grafana/dashboards/mcp-overview.json`.

### 3. HTTP Error Rate: `status=~"5.."` → `status="5xx"`
`prometheus_fastapi_instrumentator` groups status codes as string labels (`"2xx"`, `"5xx"`), not individual codes. The regex `5..` never matched.

**Fix:** Changed to exact label match `status="5xx"` in the HTTP Error Rate panel query.

### 4. Missing `status.code` dimension in OTel Collector
The "Agent Pipeline — Error Rate (%)" panel filters on `status_code="STATUS_CODE_ERROR"`. Without `status.code` in the `spanmetrics` dimensions block, the label was never attached to exported metrics.

**Fix:** Added `- name: status.code` to the `dimensions` block in `observability/otel-collector.yml`.

### 5. Monitoring preflight in `demo.sh`
The script had no check that Prometheus/Jaeger were healthy before executing, causing silent demo failures when the observability stack wasn't up.

**Fix:** Added preflight checks for Prometheus (`:9090/-/healthy`) and Jaeger (`:16686`) alongside the existing gateway health check.

## Files Changed
- `src/mcp_agent_factory/agents/analyst.py` — span attribute prefix fix
- `observability/grafana/dashboards/mcp-overview.json` — metric name and status label fixes
- `observability/otel-collector.yml` — added agent pipeline dimensions + status.code
- `scripts/demo.sh` — added monitoring preflight checks
