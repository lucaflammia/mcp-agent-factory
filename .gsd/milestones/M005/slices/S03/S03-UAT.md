# S03: Knowledge-Augmented Auction — UAT

**Milestone:** M005
**Written:** 2026-03-31T07:32:41.962Z

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: All behavior is covered by deterministic pytest tests using StubEmbedder + InMemoryVectorStore — no live server needed.

## Preconditions

- Python environment with PYTHONPATH=src set
- S01 (vector store) and S02 (ingestion) already installed
- `pytest` available

## Smoke Test

```
PYTHONPATH=src pytest tests/test_knowledge_auction.py -v -k test_auction_with_populated_store_boosts_kr
```
Expected: 1 passed — the knowledge_retrieval-capable agent outbids the plain agent when the store has a matching document.

## Test Cases

### 1. Boost applied for knowledge_retrieval agent

```
PYTHONPATH=src pytest tests/test_knowledge_auction.py -v -k "test_knowledge_boost_applied or test_auction_with_populated_store_boosts_kr"
```
1. Create InMemoryVectorStore + StubEmbedder, upsert one chunk with owner_id='test_user'
2. Create two profiles: kr_agent (capabilities=['knowledge_retrieval']) and plain_agent (no capability)
3. Run Auction.run(task, profiles, store=store, query_vector=vec, owner_id='test_user')
4. **Expected:** kr_agent wins; its bid is 1.2× higher than without the boost

### 2. No boost without capability

```
PYTHONPATH=src pytest tests/test_knowledge_auction.py -v -k test_no_boost_without_capability
```
1. Same populated store, but profile has no knowledge_retrieval capability
2. **Expected:** bid equals non-boosted score

### 3. No boost when store is None (backward compat)

```
PYTHONPATH=src pytest tests/test_knowledge_auction.py -v -k "test_no_boost_when_store_is_none or test_auction_backward_compatible"
```
1. Call Auction.run() with store=None (default)
2. **Expected:** auction returns valid BidResult, no exception

### 4. No boost when store empty

```
PYTHONPATH=src pytest tests/test_knowledge_auction.py -v -k "test_no_boost_when_store_empty or test_auction_with_empty_store_no_boost"
```
1. Store has no documents for owner_id
2. **Expected:** no boost applied, auction runs normally

### 5. Backward-compatible score() call

```
PYTHONPATH=src pytest tests/test_knowledge_auction.py -v -k test_score_backward_compatible
```
1. Call UtilityFunction.score(task, profile) with no keyword args
2. **Expected:** returns float in [0.0, 1.0] without error

### 6. Regression: existing economics tests

```
PYTHONPATH=src pytest tests/test_economics.py -v
```
**Expected:** 12 passed, no regressions in existing auction/utility behavior

## Edge Cases

### Boost clamped to 1.0

```
PYTHONPATH=src pytest tests/test_knowledge_auction.py -v -k test_boosted_score_clamped_to_one
```
1. Profile has near-perfect expertise_score so raw*1.2 would exceed 1.0
2. **Expected:** final score is 1.0, not >1.0

### Store provided without query_vector → graceful no-op

```
PYTHONPATH=src pytest tests/test_knowledge_auction.py -v -k test_auction_store_without_query_vector_no_boost
```
1. Pass store= but omit query_vector
2. **Expected:** no boost, auction completes normally

## Failure Signals

- Any test failure in test_knowledge_auction.py indicates a regression in boost logic or backward compatibility
- ImportError on VectorStore suggests S01 is not installed or PYTHONPATH is wrong
- score returning >1.0 would indicate the clamp is broken

## Not Proven By This UAT

- Live auction integration with a real embedded query from a running pipeline
- Performance of the vector probe under high load
- Multi-tenant isolation in the auction path (covered by S01 UAT)

## Notes for Tester

Auction.run() requires a pre-embedded query_vector (np.ndarray), not a raw string. S04 will need to embed task descriptions before calling the auction if it wants the boost to fire in end-to-end flows.
