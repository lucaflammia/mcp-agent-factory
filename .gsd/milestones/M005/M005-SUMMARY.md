---
id: M005
title: "RAG Layer — Vector Store, Ingestion, Augmented Auction, LibrarianAgent"
status: complete
completed_at: 2026-03-31T11:31:27.076Z
key_decisions:
  - gateway owner_id resolves from JWT sub when claims present, falls back to 'dev' for unauthenticated callers
  - Module-level singleton + set_* injection helper pattern used consistently for vector store and embedder
  - store.upsert() used directly in tests to avoid IngestionWorker bus dependency
key_files:
  - src/mcp_agent_factory/knowledge/vector_store.py
  - src/mcp_agent_factory/knowledge/embedder.py
  - src/mcp_agent_factory/knowledge/ingest.py
  - src/mcp_agent_factory/knowledge/tools.py
  - src/mcp_agent_factory/agents/librarian.py
  - src/mcp_agent_factory/agents/models.py
  - src/mcp_agent_factory/gateway/app.py
  - src/mcp_agent_factory/server_http.py
  - tests/test_vector_store.py
  - tests/test_ingest.py
  - tests/test_knowledge_auction.py
  - tests/test_s04.py
lessons_learned:
  - Always check real method signatures before writing tools that call them — VectorStore.search arg order differed from plan
  - IngestionWorker requires a bus for observability; tests that only need data in the store should use upsert() directly
  - asyncio.Queue from MessageBus.subscribe supports get_nowait/empty for sync test assertions — no need for queue.Queue wrapper
---

# M005: RAG Layer — Vector Store, Ingestion, Augmented Auction, LibrarianAgent

**Delivered vector-backed RAG layer with multi-tenant isolation, async ingestion, knowledge-augmented auction, LibrarianAgent, and SSE events across four slices**

## What Happened

M005 delivered a complete vector-backed RAG layer across four slices. S01 built the InMemoryVectorStore with cosine similarity and per-owner namespace isolation, plus the StubEmbedder. S02 added the async IngestionWorker and wired WriterAgent output auto-ingestion into the pipeline. S03 built a KnowledgeAugmentedAuction that uses RAG-retrieved context to boost agent bids. S04 exposed it all: query_knowledge_base in TOOLS, LibrarianAgent for retrieval synthesis, the gateway dispatch branch, and knowledge.retrieved SSE events. No new heavy dependencies — pure numpy throughout.

## Success Criteria Results

All success criteria met: 60+ tests pass across the RAG surface, query_knowledge_base callable via gateway, knowledge.retrieved event published to bus on every RAG call, cross-tenant isolation enforced at both storage and gateway layers.

## Definition of Done Results

- All 4 slices complete with passing tests and slice summaries written
- No regressions in existing suite (test_economics, test_pipeline, test_gateway all pass)
- Cross-tenant isolation verified at both unit and gateway integration level
- SSE event emission verified via bus subscription pattern
- All imports resolve cleanly; no new heavy dependencies added (pure numpy)

## Requirement Outcomes

All M005 requirements validated: VectorStore cosine search (test_vector_store.py), multi-tenant isolation (cross-tenant tests in S01 and S04), async ingestion (test_ingest.py), knowledge-augmented auction (test_knowledge_auction.py), LibrarianAgent + gateway tool + SSE event (test_s04.py).

## Deviations

Minor: VectorStore.search signature was (owner_id, query_vector, top_k) not (query_vector, owner_id, top_k) as planned — adapted in tools.py. IngestionWorker requires a bus arg so tests use store.upsert() directly. bus.subscribe returns asyncio.Queue, not a plain queue — tests adapted to q.empty()/q.get_nowait() pattern.

## Follow-ups

- Switch from symmetric HS256 JWT to RS256 + JWKS for multi-service deployments (noted in M002 knowledge)
- Evaluate Content-Length MCP wire framing for full spec compatibility with official MCP clients
- Consider persisting InMemoryVectorStore to disk for durability across restarts
