# RAG Pipeline — Sub-Issue Changelog

All RAG sub-issues shipped on the `rag-prod` branch and collected into `main` via a single PR.

---

## RAG-03: Guarded Retrieval ✅

**Goal:** Enforce tenant isolation at the query layer, not post-hoc.

| Feature | Detail |
|---------|--------|
| Tenant validation | Missing tenant raises `ValueError` before ANN search |
| Mandatory filters | Tenant, ACL, date filters applied inside the ANN call |
| Embedder version check | Query `embedder_id` must match index; mismatch raises explicit error |
| Cross-encoder reranking | top-100 ANN → rerank to 10 → MMR diversification to 5 (configurable) |
| OTel spans | filter resolution, ANN, reranking, MMR |

**Key file:** `src/mcp_agent_factory/knowledge/query_handler.py`  
**Tests:** 59 tests — cross-tenant isolation, embedder gating, MMR, date filters, OTel.

---

## RAG-04: Validated Generation with Citation Checks ✅

**Goal:** Zero hallucinated citations in LLM-generated answers.

| Feature | Detail |
|---------|--------|
| Pydantic schema | `RagAnswer(answer, cited_chunk_ids, refused, refusal_reason)` |
| Citation validation | Every cited chunk ID must exist in retrieved set |
| Retry logic | Retry once on validation failure; refuse on second failure |
| Provider-independent | Same logic across Anthropic, OpenAI, Ollama, Bedrock |
| Telemetry | OTel spans + Prometheus counters for failures, retries, refusals |

**Key file:** `src/mcp_agent_factory/knowledge/generation.py`  
**Tests:** 39 tests — valid answers, invalid citations, malformed JSON, empty retrieval, retry paths.

---

## RAG-05: Embedder Versioning and Dual-Write Cutover ✅

**Goal:** Safe embedding model upgrades without silent quality degradation.

| Feature | Detail |
|---------|--------|
| Version isolation | Every chunk stores `embedder_id`; queries only search matching version |
| Mismatch detection | Explicit `ValueError` instead of silent empty results |
| Dual-write cutover | `IdempotentIngestionPipeline.dual_write()` writes old + new in parallel |
| Content-hash dedup | Skips `(owner_id, chunk_id, embedder_id)` triples already present |
| Config-only rollback | Change `embedder_id` in query context; no re-ingest needed |

**Key file:** `src/mcp_agent_factory/knowledge/ingest.py`  
**Documentation:** [`docs/RAG/RAG-05-EMBEDDER-VERSIONING.md`](RAG-05-EMBEDDER-VERSIONING.md)  
**Tests:** 11 tests — version isolation, mismatch errors, dual-write, rollback, backfill.

---

## RAG-06: Evaluation Gates and Operations ✅

**Goal:** Operational confidence layer: CI eval gate, dashboards, runbooks.

| Feature | Detail |
|---------|--------|
| Golden-set eval gate | `evals/datasets/*.jsonl` versioned; CI fails on >5% regression vs baseline |
| Nightly CI | Runs evals on every push + nightly at 02:00 UTC |
| Split metrics | Retrieval (recall/MRR/nDCG) vs generation (groundedness/refusal) reported separately |
| Grafana dashboards | `observability/grafana/dashboards/rag-metrics.json` — score distribution, refusal rate, baseline delta |
| Backup/restore | `PgVectorStore.backup()` / `.restore()` with documented drill |
| Right to be forgotten | `delete_by_data_subject()`, `delete_by_source_id()` |
| Weekly compaction | `PgVectorStore.compact()` scheduled every Monday 02:00 UTC |

**Key file:** `src/mcp_agent_factory/knowledge/vector_store.py`  
**Documentation:** [`docs/RAG/RAG-06-EVALUATION-GATES-AND-OPERATIONS.md`](RAG-06-EVALUATION-GATES-AND-OPERATIONS.md)  
**Tests:** 29 tests — backup/restore, deletion, compaction, search filters, MMR, connection management.

---

## RAG-07: Vector Visualization Dashboard ✅

**Goal:** Similarity-score visibility in Grafana. No new AWS services or paid dependencies.

| Panel | Metric |
|-------|--------|
| Chunks in Index | `rag_index_chunk_count` gauge |
| Empty Result Rate | ratio of zero-result queries |
| Refusal Rate | ratio of refused queries |
| Similarity Score Distribution | per-query score histogram |
| Best Match Score Per Query | `rag_top1_score` gauge per tenant |

**Setup:** `docker compose --profile full up -d`  
**Dashboard:** `http://localhost:3000/d/rag-metrics`  
**Verification guide:** [`docs/RAG/RAG-07-VERIFICATION-GUIDE.md`](RAG-07-VERIFICATION-GUIDE.md)

---

## RAG-08: Query Management — Rate Limiting, Quotas, Audit Logging ✅

**Goal:** Per-tenant controls and audit visibility on the RAG `/query` endpoint.

| Layer | Mechanism | Enforced |
|-------|-----------|----------|
| Rate limit | Token bucket per tenant | Before retrieval |
| Quota | Daily + hourly counters (UTC) | Before retrieval |
| Audit log | Full query metadata → Redis (24h TTL) | After generation |

**New endpoints:**

| Endpoint | Description |
|----------|-------------|
| `GET /query/stats/{tenant}` | Aggregated 24h stats |
| `POST /admin/quota/{tenant}` | Update rate limit / quota at runtime |
| `GET /admin/quotas` | List all per-tenant quota configs |

**Key file:** `src/mcp_agent_factory/gateway/query_management.py`  
**Documentation:** [`docs/QUERY_MANAGEMENT.md`](../QUERY_MANAGEMENT.md)

---

## RAG-09: Query Management Enhancements ✅

**Goal:** Unblock production multi-tenant deployments: durable audit logs, timezone-aware quotas, cost-based limiting.

### S1 — PostgreSQL Durable Audit Log

| Feature | Detail |
|---------|--------|
| Partitioned table | `migrations/004_audit_log_partition.sql` |
| Async batch writer | 10s flush or 1 000 entries; p99 write latency < 100ms |
| Graceful fallback | Redis-only if PostgreSQL unavailable |
| Export endpoint | `GET /query/audit/{tenant}?start=YYYY-MM-DD&end=YYYY-MM-DD&fmt=json\|csv` |

**Env var:** `AUDIT_DB_URL=postgresql://user:pass@host/db`

### S2 — Timezone-Aware Quota Windows

| Feature | Detail |
|---------|--------|
| Per-tenant timezone | Stored via `POST /admin/quota/{tenant}` with `timezone` field |
| DST handling | Uses Python `zoneinfo` stdlib; no double-resets or gaps |
| Validation | Invalid IANA timezone string → `400` immediately |
| Default | UTC (backward-compatible) |

### S3 — Cost-Based Rate Limiting

| Feature | Detail |
|---------|--------|
| Variable cost | `1.0 + (top_k−1)×0.1 + (latency_ms/100)×0.1 + 0.5×refused + retries×0.25` |
| 429 on over-limit | `Retry-After = cost/QPS` |
| Stats | `cost_p50`, `cost_p99` on stats endpoint |
| Prometheus | `rag_query_cost_tokens` histogram |
| Tunable weights | `COST_TOP_K_PER_UNIT`, `COST_LATENCY_MS_PER_100`, `COST_REFUSAL_PENALTY`, `COST_RETRY_PENALTY` |

**Documentation:** [`docs/QUERY_MANAGEMENT.md`](../QUERY_MANAGEMENT.md), [`docs/RAG/QUERY-MANAGEMENT-QUICKSTART.md`](QUERY-MANAGEMENT-QUICKSTART.md), [`docs/STORAGE-VERIFICATION.md`](../STORAGE-VERIFICATION.md)  
**Tests:** 353 tests across `tests/test_query_management.py`, `tests/test_rag_query_management.py`, `tests/test_timezone_quota.py`, `tests/test_cost_limiter.py`.
