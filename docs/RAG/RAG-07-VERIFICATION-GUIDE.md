# RAG Production Pipeline — Verification Guide

This guide walks through verifying every acceptance criterion for the production RAG pipeline (RAG-02 through RAG-06).

---

## Prerequisites

```bash
# Install dependencies (includes sentence-transformers for 384-dim embeddings)
pip install -e ".[dev]"
pip install sentence-transformers psycopg[binary]

# Start supporting services (Postgres + pgvector, Redis, Prometheus, Grafana)
docker-compose up -d

# Run DB migrations
psql $DATABASE_URL -f migrations/001_pgvector_init.sql
psql $DATABASE_URL -f migrations/002_rag05_embedder_versioning.sql
psql $DATABASE_URL -f migrations/003_rag_source_id.sql
```

---

## 1. Idempotent Ingestion (RAG-02)

### Run ingestion twice, expect no duplicates

```bash
# First ingest
python -m mcp_agent_factory.knowledge.ingest --source data/samples/finance_q3_2024.pdf

# Second ingest of same file — must be a no-op (same content_hash)
python -m mcp_agent_factory.knowledge.ingest --source data/samples/finance_q3_2024.pdf
```

**Expected:** second run logs `Skipping chunk <id>: content_hash already exists` for every chunk; row count in `chunks` table is unchanged.

### Verify chunk metadata

```sql
SELECT owner_id, embedder_id, content_hash, source_id FROM chunks LIMIT 5;
```

All four columns must be non-null (or source_id may be null for backfilled rows).

### Verify PII scrubbing

```bash
python -m pytest tests/test_rag02_idempotent_ingestion.py -v -k "pii"
```

---

## 2. Guarded Retrieval (RAG-03)

### Tenant isolation smoke test

```bash
python -m pytest tests/test_pgvector_store.py -v -k "tenant"
```

A query with `tenant=A` must return zero results for chunks ingested under `tenant=B`.

### Full RAG-02 / ingestion test suite

```bash
python -m pytest tests/test_rag02_idempotent_ingestion.py tests/test_ingest.py -v
```

---

## 3. Validated Generation with Citations (RAG-04)

### Schema validation and citation check

```bash
python -m pytest tests/test_rag04_validated_generation.py -v
```

Inject a question with known source chunks; assert the response includes `citations` referencing the correct `chunk_id` values and passes schema validation.

---

## 4. Embedder Versioning and Dual-Write Cutover (RAG-05)

### Version recorded in every embedding, dual-write, and cutover

```bash
python -m pytest tests/test_rag05_embedder_versioning.py -v
```

---

## 5. Evaluation Gates (RAG-06)

### Run the eval harness against the golden set

```bash
python -m evals.runner --dataset rag_qa --tag manual-run
```

Output must include `golden_set_version` in `meta` and separate `retrieval` / `generation` metric blocks.

### Simulate a quality regression

```bash
# Compare two run tags — the compare tool exits non-zero on regression
python -m evals.compare baseline manual-run

# To see raw JSON diff
python -m evals.compare baseline manual-run --json
```

Run tags are set via `--tag` when calling `evals.runner`. The baseline tag is `baseline` (file: `evals/results/baseline.json`).

---

## 6. Operations (RAG-06)

### Backup and restore drill

```bash
python -c "
import asyncio
from mcp_agent_factory.knowledge.vector_store import PgVectorStore
import os

store = PgVectorStore(os.environ['DATABASE_URL'])

async def drill():
    path = await store.backup('/tmp/rag-backup-drill.sql')
    print(f'Backup written to {path}')
    await store.restore(path)
    print('Restore complete')

asyncio.run(drill())
"
```

Record the restore time. This satisfies the documented backup/restore drill requirement.

### Right to be forgotten

```bash
python -c "
import asyncio
from mcp_agent_factory.knowledge.vector_store import PgVectorStore
import os

store = PgVectorStore(os.environ['DATABASE_URL'])

async def rtbf():
    # Delete by source
    deleted = await store.delete_by_source_id('finance_q3_2024.pdf')
    print(f'Deleted {deleted} chunks by source_id')

    # Verification query — must return 0 results
    results = await store.search('finance Q3 revenue', filters={'source_id': 'finance_q3_2024.pdf'})
    assert len(results) == 0, f'Expected 0 results, got {len(results)}'
    print('Verification query returned 0 results — RTBF confirmed')

asyncio.run(rtbf())
"
```

### Weekly compaction

```bash
python -c "
import asyncio
from mcp_agent_factory.knowledge.vector_store import PgVectorStore
import os

store = PgVectorStore(os.environ['DATABASE_URL'])
asyncio.run(store.compact())
print('Compaction complete')
"
```

---

## 7. Observability and Grafana Dashboards (RAG-07)

### Prerequisites: start the full stack

```bash
docker compose --profile full up -d
# If Grafana was already running without the Infinity plugin, force a restart:
docker compose restart grafana
# Wait ~30 s for the plugin to download, then verify:
docker compose logs grafana | grep -i "infinity\|plugin"
```

Expected log line: `Plugin registered: yesoreyeram-infinity-datasource`.

---

### Panel 1 — Similarity Score Distribution

**What it shows:** histogram of cosine similarity scores across all retrieved chunks, bucketed from 0.5–1.0.

**How to trigger data:**
```bash
# Run a few queries so Prometheus has histogram observations
for q in "revenue Q3" "net income" "operating margin" "cash flow"; do
  curl -s -X POST http://localhost:8000/rag/query \
    -H 'Content-Type: application/json' \
    -d "{\"question\": \"$q\", \"tenant\": \"default\"}" > /dev/null
done
```

**What to verify:**
1. Open `http://localhost:3000/d/rag-metrics` → **Similarity Score Distribution** panel.
2. Set time range to **Last 5 minutes**.
3. Bars should appear in the 0.7–0.9 bucket range for typical document queries.
4. Run `curl -s http://localhost:9090/api/v1/query?query=rag_retrieval_score_bucket | python -m json.tool | head -30` — confirm non-zero counts in multiple buckets.

---

### Panel 2 — Top-1 Similarity Score Over Time

**What it shows:** the cosine similarity of the highest-ranked chunk for each query, plotted as a time series.

**How to trigger data:** same queries as Panel 1 (the gauge updates on every retrieval).

**What to verify:**
1. **Top-1 Similarity Score Over Time** panel shows a line with values between 0 and 1.
2. Confirm the gauge is live:
   ```bash
   curl -s http://localhost:8000/metrics | grep rag_top1_score
   # Expected: rag_top1_score{tenant="default"} 0.8x
   ```
3. Each new query shifts the gauge — run one more query and watch the value update within the 15 s Prometheus scrape interval.

---

### Panel 3 — Score Heatmap (percentile × time)

**What it shows:** bucket distribution over time as a heatmap — darker cells indicate more chunks scoring in that similarity band.

**How to trigger data:** generate ~20 queries to accumulate enough histogram data points:
```bash
for i in $(seq 1 20); do
  curl -s -X POST http://localhost:8000/rag/query \
    -H 'Content-Type: application/json' \
    -d "{\"question\": \"test query $i\", \"tenant\": \"default\"}" > /dev/null
done
```

**What to verify:**
1. **Score Heatmap** panel — set time range to **Last 15 minutes**.
2. Colored bands should appear in the 0.6–0.9 similarity range.
3. If the panel shows "No data", check Prometheus is scraping the gateway:
   ```bash
   curl -s 'http://localhost:9090/api/v1/targets' | python -m json.tool | grep -A5 '"gateway"'
   ```

---

### Panel 4 — Vector Cluster View (2D UMAP)

**What it shows:** 2D scatter plot of the query vector (highlighted) alongside its top-k retrieved chunks and a random background sample, projected with UMAP.

**Prerequisites:** the index must have at least 4 chunks (UMAP requires >3 points). Ingest the sample PDF first if needed:
```bash
python -m mcp_agent_factory.knowledge.ingest \
  --source data/samples/finance_q3_2024.pdf \
  --tenant default
```

**Verify the endpoint directly:**
```bash
curl -s "http://localhost:8000/rag/visualize?q=revenue&tenant=default&k=5&flat=1" | python -m json.tool | head -40
```

Expected shape:
```json
{
  "points": [
    {"x": 0.42, "y": -0.18, "label": "query",    "score": null, "kind": "query",      "preview": "revenue"},
    {"x": 0.51, "y": -0.11, "label": "doc:abc",   "score": 0.91, "kind": "result",     "preview": "..."},
    {"x": -0.3, "y": 0.72,  "label": "bg:xyz",    "score": null, "kind": "background", "preview": "..."}
  ]
}
```

**Verify in Grafana:**
1. **Vector Cluster View (2D UMAP)** panel → set time range to **Now**.
2. The Infinity datasource calls `http://gateway:8000/rag/visualize?q=test&tenant=default&k=10&flat=1`.
3. A table of x/y/label/score/kind columns should render.
4. To change the query term, edit the panel → Targets → URL, change `q=test` to your query, then **Apply**.

**Plugin not found error:** if the panel shows "Panel plugin not found: yesoreyeram-infinity-datasource":
```bash
# Restart Grafana to force plugin download
docker compose restart grafana
# Wait 30s then reload the browser
```
The `GF_INSTALL_PLUGINS=yesoreyeram-infinity-datasource` env var in `docker-compose.yml` triggers the download at container startup. The plugin is free and open-source (no account required).

---

### Alert simulation

```bash
# Trigger a burst of refusals by querying out-of-scope questions in a loop
for i in $(seq 1 20); do
  curl -s -X POST http://localhost:8000/query \
    -H 'Content-Type: application/json' \
    -d '{"question": "out-of-scope '"$i"'", "tenant": "test"}' > /dev/null
done
# Check Prometheus alert manager for RAG refusal spike alert firing
curl -s http://localhost:9090/api/v1/alerts | python -m json.tool | grep -A3 "refusal"
```

---

## 8. Full Test Suite

```bash
pytest tests/ -v --tb=short
```

All tests must pass with no failures.

---

## 9. CI Nightly Eval Gate

The nightly job runs automatically at `02:00 UTC` via `.github/workflows/ci.yml`. To trigger it manually:

```bash
gh workflow run ci.yml --ref rag-prod
```

Monitor the run:

```bash
node scripts/ci_monitor.cjs runs --branch rag-prod
node scripts/ci_monitor.cjs watch <run-id>
```

A regression beyond 5% on any metric causes a non-zero exit and marks the run red.
