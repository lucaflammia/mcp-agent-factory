# M005: Neural Knowledge Integration (RAG)

**Gathered:** 2026-03-31
**Status:** Ready for planning

## Project Description

Add a vector-backed RAG layer to the existing MCP Agent Factory multi-agent ecosystem. The system already has: Analyst→Writer pipeline, MessageBus, OAuth-secured gateway, auction-based task allocation. M005 adds persistent cross-session memory, multi-tenant retrieval, knowledge-aware bidding, and a new LibrarianAgent.

## Why This Milestone

The existing pipeline is stateless between sessions — each task starts from scratch. M005 gives the ecosystem "long-term memory": WriterAgent outputs are auto-indexed, future tasks retrieve relevant prior work, and the auction favours agents that can exploit that stored knowledge.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Call `query_knowledge_base` via `mcp_call` and receive semantically relevant chunks from prior agent reports
- Run the pipeline, see WriterAgent output auto-indexed, then query it back in the same or a future session
- Observe `knowledge_retrieved` SSE events streaming from the gateway during RAG queries
- Trust that user A's indexed data is never visible to user B (owner isolation enforced at every upsert/query)

### Entry point / environment

- Entry point: `mcp_call("agent-factory", "query_knowledge_base", {"query": "...", "owner_id": "..."})` via running gateway
- Environment: local dev with `MCP_DEV_MODE=1`
- Live dependencies involved: MessageBus (existing), FakeRedis (existing), InMemoryVectorStore (new, no external service)

## Completion Class

- Contract complete means: pytest tests/ passes — all unit + integration tests green across all M005 modules
- Integration complete means: `query_knowledge_base` callable via live gateway; WriterAgent output flows through bus → ingest → store → retrieval round-trip
- Operational complete means: none (no daemon/service lifecycle changes)

## Final Integrated Acceptance

- Run the full Analyst→Writer pipeline; verify the report is indexed; call `query_knowledge_base` and get back relevant chunks
- Query as user B after indexing as user A → empty result (isolation proof)
- SSE stream emits `knowledge_retrieved` event during a gateway RAG query

## Risks and Unknowns

- **Embedding quality with stub embedder** — random projection won't produce semantically meaningful retrieval; stub is for test structure only; real quality requires sentence-transformers or similar (out of scope for this milestone)
- **Cosine similarity correctness** — pure numpy implementation must match expected ranking behaviour; needs careful test coverage
- **MessageBus topic contract** — `agent.output.final` is a new topic; WriterAgent must publish to it; need to add that publish call without breaking existing tests

## Existing Codebase / Prior Art

- `src/mcp_agent_factory/agents/writer.py` — WriterAgent; must add `bus.publish("agent.output.final", ...)` after report generation
- `src/mcp_agent_factory/economics/utility.py` — `UtilityFunction.score()` — needs knowledge-aware branch (+20% for `knowledge_retrieval` capability)
- `src/mcp_agent_factory/economics/auction.py` — `Auction` — needs shallow vector probe before scoring
- `src/mcp_agent_factory/messaging/bus.py` — `MessageBus`, `AgentMessage` — Ingestion Worker subscribes here
- `src/mcp_agent_factory/messaging/sse_v1_router.py` — add `knowledge_retrieved` event type
- `src/mcp_agent_factory/gateway/app.py` — add `query_knowledge_base` tool handler + TOOLS registration
- `src/mcp_agent_factory/agents/models.py` — `AgentTask`, `MCPContext` — LibrarianAgent follows same pattern
- `src/mcp_agent_factory/auth/resource.py` — `make_verify_token` — `claims['sub']` is the owner_id source

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions.

## Relevant Requirements

- R101 — Multi-tenant isolation is the security spine of the entire knowledge layer
- R102 — Auto-ingestion is the primary mechanism that populates the knowledge store
- R103 — Knowledge-augmented bidding is the economic payoff of having the store
- R104, R105 — Gateway tool and LibrarianAgent are the external-facing surface
- R106, R107 — SSE events and protocol abstraction are cross-cutting concerns

## Scope

### In Scope

- `knowledge/vector_store.py` — VectorStore protocol + InMemoryVectorStore (numpy cosine similarity)
- `knowledge/embedder.py` — Embedder protocol + StubEmbedder (deterministic hash projection)
- `knowledge/ingest.py` — IngestionWorker (MessageBus subscriber on `agent.output.final`)
- `knowledge/tools.py` — `query_knowledge_base` function used by gateway and LibrarianAgent
- `agents/librarian.py` — LibrarianAgent
- Updates to `economics/utility.py` and `economics/auction.py` for knowledge-aware bidding
- Updates to `messaging/sse_v1_router.py` for `knowledge_retrieved` event
- Updates to `gateway/app.py` for new tool registration
- Updates to `agents/writer.py` to publish `agent.output.final`

### Out of Scope / Non-Goals

- Real embedding models (sentence-transformers, OpenAI embeddings)
- External vector databases (Qdrant, ChromaDB, pgvector)
- Source URI / S3 tracking on chunks
- Chunk persistence across process restarts (in-memory only)

## Technical Constraints

- No new heavy dependencies — numpy is already available; all new code must work with existing `pip install -e .`
- Tab indentation throughout (project convention)
- Protocol/stub pattern: VectorStore and Embedder are protocols; InMemoryVectorStore and StubEmbedder are the default implementations
- `owner_id` always derived from JWT `sub` — never passed as a user-supplied parameter in authenticated flows

## Integration Points

- MessageBus — IngestionWorker subscribes to `agent.output.final`; SSE router publishes `knowledge_retrieved`
- OAuth resource middleware — `claims['sub']` → `owner_id` for namespace isolation
- Gateway `/mcp` endpoint — `query_knowledge_base` registered as a new tool
- Auction — shallow vector probe before utility scoring

## Open Questions

- None — design confirmed in discussion.
