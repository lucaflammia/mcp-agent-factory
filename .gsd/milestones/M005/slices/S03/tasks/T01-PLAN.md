---
estimated_steps: 8
estimated_files: 2
skills_used: []
---

# T01: Add knowledge_boost to UtilityFunction and wire vector probe into Auction

Modify `UtilityFunction.score()` to accept an optional `knowledge_boost: bool = False` parameter. When True and `'knowledge_retrieval' in profile.capabilities`, multiply `raw` by 1.2 BEFORE clamping. Modify `Auction.__init__` and `Auction.run()` to accept optional `store: VectorStore | None = None` and `owner_id: str = ''`. Before computing bids, if `store` is not None, call `store.search(query=task.name, owner_id=owner_id, top_k=1)`; if results are non-empty, pass `knowledge_boost=True` to `_utility.score()` for each profile that has `'knowledge_retrieval'` in capabilities.

Constraints:
- Tab indentation throughout (project convention)
- `score()` signature must be backward-compatible: existing callers that pass no knowledge args continue to work
- `Auction.run()` must be backward-compatible: `store=None` and `owner_id=''` defaults
- Boost: `raw * 1.2` then `max(0.0, min(1.0, ...))`
- Import `VectorStore` from `mcp_agent_factory.knowledge.vector_store` — one-way dependency, no cycle
- Do NOT add `knowledge_boost` to the bid log: the existing log structure must remain unchanged for downstream consumers

## Inputs

- ``src/mcp_agent_factory/economics/utility.py``
- ``src/mcp_agent_factory/economics/auction.py``
- ``src/mcp_agent_factory/knowledge/vector_store.py``

## Expected Output

- ``src/mcp_agent_factory/economics/utility.py``
- ``src/mcp_agent_factory/economics/auction.py``

## Verification

PYTHONPATH=src python -c "from mcp_agent_factory.economics.utility import UtilityFunction, AgentProfile; from mcp_agent_factory.agents.models import AgentTask; u=UtilityFunction(); p=AgentProfile(agent_id='a', capabilities=['knowledge_retrieval'], expertise_score=0.5, cost_per_unit=1.0); t=AgentTask(id='t1', name='test', required_capability='analysis', complexity=0.0); s_no=u.score(t,p); s_yes=u.score(t,p,knowledge_boost=True); assert s_yes > s_no, f'{s_yes} not > {s_no}'; print('OK')"
