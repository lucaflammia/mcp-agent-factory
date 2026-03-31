# S03: Knowledge-Augmented Auction

**Goal:** Add a shallow vector probe to the auction cycle and a +20% utility boost for agents with `knowledge_retrieval` capability when relevant context is found. Wire `InMemoryVectorStore` from S01 into `Auction.run()` via optional parameters, and update `UtilityFunction.score()` with a backward-compatible `knowledge_boost` flag.
**Demo:** After this: pytest tests/test_knowledge_auction.py -v passes; pytest tests/test_economics.py still passes

## Tasks
- [x] **T01: Added backward-compatible knowledge_boost to UtilityFunction.score() and wired optional vector probe into Auction.run() with +20% utility boost for knowledge_retrieval agents** — Modify `UtilityFunction.score()` to accept an optional `knowledge_boost: bool = False` parameter. When True and `'knowledge_retrieval' in profile.capabilities`, multiply `raw` by 1.2 BEFORE clamping. Modify `Auction.__init__` and `Auction.run()` to accept optional `store: VectorStore | None = None` and `owner_id: str = ''`. Before computing bids, if `store` is not None, call `store.search(query=task.name, owner_id=owner_id, top_k=1)`; if results are non-empty, pass `knowledge_boost=True` to `_utility.score()` for each profile that has `'knowledge_retrieval'` in capabilities.

Constraints:
- Tab indentation throughout (project convention)
- `score()` signature must be backward-compatible: existing callers that pass no knowledge args continue to work
- `Auction.run()` must be backward-compatible: `store=None` and `owner_id=''` defaults
- Boost: `raw * 1.2` then `max(0.0, min(1.0, ...))`
- Import `VectorStore` from `mcp_agent_factory.knowledge.vector_store` — one-way dependency, no cycle
- Do NOT add `knowledge_boost` to the bid log: the existing log structure must remain unchanged for downstream consumers
  - Estimate: 30m
  - Files: src/mcp_agent_factory/economics/utility.py, src/mcp_agent_factory/economics/auction.py
  - Verify: PYTHONPATH=src python -c "from mcp_agent_factory.economics.utility import UtilityFunction, AgentProfile; from mcp_agent_factory.agents.models import AgentTask; u=UtilityFunction(); p=AgentProfile(agent_id='a', capabilities=['knowledge_retrieval'], expertise_score=0.5, cost_per_unit=1.0); t=AgentTask(id='t1', name='test', required_capability='analysis', complexity=0.0); s_no=u.score(t,p); s_yes=u.score(t,p,knowledge_boost=True); assert s_yes > s_no, f'{s_yes} not > {s_no}'; print('OK')"
- [x] **T02: All 8 knowledge-auction tests and 12 regression tests pass (20 total) confirming the +20% boost path and backward compatibility** — Create `tests/test_knowledge_auction.py` with pytest cases that exercise the +20% boost path and the no-boost fallback:

1. `test_knowledge_boost_applied` — create an `InMemoryVectorStore` + `StubEmbedder`, upsert one chunk with `owner_id='test_user'`, create an `AgentProfile` with `capabilities=['knowledge_retrieval']` and a second profile without it, run `Auction.run(task, profiles, store=store, owner_id='test_user')` — assert the retrieval-capable agent's bid reflects the boost
2. `test_no_boost_without_capability` — same setup but profile has no `knowledge_retrieval` capability — assert bid is same as without store
3. `test_no_boost_when_store_is_none` — pass `store=None` (default) — assert auction runs normally and returns a valid BidResult
4. `test_no_boost_when_store_empty` — store has no documents for the `owner_id` — assert no boost applied
5. `test_backward_compat_score` — call `UtilityFunction.score(task, profile)` with no keyword args — assert it returns a float in [0.0, 1.0]

Use `StubEmbedder` + `InMemoryVectorStore` directly (no mocks needed). Import from `mcp_agent_factory.knowledge` and `mcp_agent_factory.economics`. All tests must pass with `PYTHONPATH=src pytest tests/test_knowledge_auction.py -v`. Then confirm no regressions: `PYTHONPATH=src pytest tests/test_economics.py -v`.
  - Estimate: 30m
  - Files: tests/test_knowledge_auction.py
  - Verify: PYTHONPATH=src pytest tests/test_knowledge_auction.py tests/test_economics.py -v
