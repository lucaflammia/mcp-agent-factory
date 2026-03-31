---
estimated_steps: 7
estimated_files: 1
skills_used: []
---

# T02: Write tests/test_knowledge_auction.py and verify no regressions

Create `tests/test_knowledge_auction.py` with pytest cases that exercise the +20% boost path and the no-boost fallback:

1. `test_knowledge_boost_applied` — create an `InMemoryVectorStore` + `StubEmbedder`, upsert one chunk with `owner_id='test_user'`, create an `AgentProfile` with `capabilities=['knowledge_retrieval']` and a second profile without it, run `Auction.run(task, profiles, store=store, owner_id='test_user')` — assert the retrieval-capable agent's bid reflects the boost
2. `test_no_boost_without_capability` — same setup but profile has no `knowledge_retrieval` capability — assert bid is same as without store
3. `test_no_boost_when_store_is_none` — pass `store=None` (default) — assert auction runs normally and returns a valid BidResult
4. `test_no_boost_when_store_empty` — store has no documents for the `owner_id` — assert no boost applied
5. `test_backward_compat_score` — call `UtilityFunction.score(task, profile)` with no keyword args — assert it returns a float in [0.0, 1.0]

Use `StubEmbedder` + `InMemoryVectorStore` directly (no mocks needed). Import from `mcp_agent_factory.knowledge` and `mcp_agent_factory.economics`. All tests must pass with `PYTHONPATH=src pytest tests/test_knowledge_auction.py -v`. Then confirm no regressions: `PYTHONPATH=src pytest tests/test_economics.py -v`.

## Inputs

- ``src/mcp_agent_factory/economics/utility.py``
- ``src/mcp_agent_factory/economics/auction.py``
- ``src/mcp_agent_factory/knowledge/vector_store.py``
- ``src/mcp_agent_factory/knowledge/embedder.py``
- ``tests/test_economics.py``

## Expected Output

- ``tests/test_knowledge_auction.py``

## Verification

PYTHONPATH=src pytest tests/test_knowledge_auction.py tests/test_economics.py -v
