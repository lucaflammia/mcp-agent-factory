---
id: T01
parent: S01
milestone: M006
provides: []
requires: []
affects: []
key_files: ["src/mcp_agent_factory/streams/__init__.py", "src/mcp_agent_factory/streams/worker.py", "tests/test_m006_streams.py"]
key_decisions: ["Pass streams as keyword dict in xreadgroup to avoid fakeredis 2.34.1 TypeError on positional args"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "pytest tests/test_m006_streams.py -v — 3 passed in 1.12s"
completed_at: 2026-04-01T14:20:49.186Z
blocker_discovered: false
---

# T01: Add StreamWorker with XREADGROUP claim/ACK/PEL recovery and passing fakeredis tests

> Add StreamWorker with XREADGROUP claim/ACK/PEL recovery and passing fakeredis tests

## What Happened
---
id: T01
parent: S01
milestone: M006
key_files:
  - src/mcp_agent_factory/streams/__init__.py
  - src/mcp_agent_factory/streams/worker.py
  - tests/test_m006_streams.py
key_decisions:
  - Pass streams as keyword dict in xreadgroup to avoid fakeredis 2.34.1 TypeError on positional args
duration: ""
verification_result: passed
completed_at: 2026-04-01T14:20:49.188Z
blocker_discovered: false
---

# T01: Add StreamWorker with XREADGROUP claim/ACK/PEL recovery and passing fakeredis tests

**Add StreamWorker with XREADGROUP claim/ACK/PEL recovery and passing fakeredis tests**

## What Happened

Created src/mcp_agent_factory/streams/__init__.py and streams/worker.py with StreamWorker implementing ensure_group, publish, claim_one (streams as keyword dict), ack, and recover. Wrote tests/test_m006_streams.py with three test cases covering R001 (claim+ack clears PEL) and R002 (PEL crash recovery via xclaim). All tests pass against fakeredis 2.34.1.

## Verification

pytest tests/test_m006_streams.py -v — 3 passed in 1.12s

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -m pytest tests/test_m006_streams.py -v` | 0 | ✅ pass | 1120ms |


## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/mcp_agent_factory/streams/__init__.py`
- `src/mcp_agent_factory/streams/worker.py`
- `tests/test_m006_streams.py`


## Deviations
None.

## Known Issues
None.
