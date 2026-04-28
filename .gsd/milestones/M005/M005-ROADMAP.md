# M005: 

## Vision
Add a vector-backed RAG layer to the MCP Agent Factory: persistent cross-session memory via auto-ingestion of WriterAgent outputs, multi-tenant namespace isolation bound to JWT sub claims, knowledge-augmented auction bidding, a LibrarianAgent for retrieval synthesis, and real-time SSE knowledge_retrieved events — all built on a pure-numpy in-memory store with no new heavy dependencies.

## Slice Overview
| ID | Slice | Risk | Depends | Done | After this |
|----|-------|------|---------|------|------------|
| S01 | Vector Store + Multi-Tenant Middleware | high | — | ✅ | pytest tests/test_vector_store.py -v passes — cosine ranking correct, cross-tenant query returns empty |
| S02 | Async Ingestion Worker | medium | S01 | ✅ | pytest tests/test_ingest.py -v passes; pytest tests/test_pipeline.py still passes (no regressions) |
| S03 | Knowledge-Augmented Auction | medium | S01 | ✅ | pytest tests/test_knowledge_auction.py -v passes; pytest tests/test_economics.py still passes |
| S04 | LibrarianAgent + Gateway Tool + SSE Events | low | S01, S02, S03 | ✅ | mcp_call(server='agent-factory', tool='query_knowledge_base', args={...}) returns chunks; SSE stream shows knowledge_retrieved event |
