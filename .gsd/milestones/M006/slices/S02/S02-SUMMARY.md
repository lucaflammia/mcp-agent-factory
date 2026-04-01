---
id: S02
parent: M006
milestone: M006
provides:
  - EventLog Protocol (append/read interface)
  - InProcessEventLog (in-memory, async, no deps)
  - session_topic(session_id) helper
  - capability_topic(capability) helper
  - KafkaEventLog stub (guarded aiokafka import)
  - tests/test_m006_eventlog.py proving R003/R004/R005
requires:
  - slice: S01
    provides: streams package scaffolding and fakeredis test patterns
affects:
  - S04
key_files:
  - src/mcp_agent_factory/streams/eventlog.py
  - src/mcp_agent_factory/streams/kafka_adapter.py
  - src/mcp_agent_factory/streams/__init__.py
  - tests/test_m006_eventlog.py
key_decisions:
  - InProcessEventLog uses asyncio.Lock + defaultdict; offset is an integer index into the stored list — simple and sufficient for in-process testing
  - KafkaEventLog guards aiokafka import so the package stays importable without aiokafka installed — swap-in pattern for R017
patterns_established:
  - EventLog Protocol + InProcessEventLog pattern: define a Protocol for append(topic, event) / read(topic, offset), back it with an in-memory defaultdict list — zero external deps, fully async, trivially replaceable with a real broker adapter
observability_surfaces:
  - none
drill_down_paths:
  - .gsd/milestones/M006/slices/S02/tasks/T01-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-04-01T14:26:36.771Z
blocker_discovered: false
---

# S02: Event Log Abstraction + Partitioned Topics

**Added EventLog Protocol, InProcessEventLog, TopicRouter helpers (session_topic/capability_topic), and KafkaEventLog stub; 3 tests prove R003/R004/R005.**

## What Happened

Single task (T01) delivered the full slice goal. Created `src/mcp_agent_factory/streams/eventlog.py` with: the `EventLog` Protocol, `InProcessEventLog` (asyncio.Lock + defaultdict, integer offset index), and `session_topic`/`capability_topic` helper functions. Created `src/mcp_agent_factory/streams/kafka_adapter.py` as a `KafkaEventLog` stub with a guarded `aiokafka` import so the package stays importable without the broker library installed. Updated `src/mcp_agent_factory/streams/__init__.py` to export all new symbols. Wrote `tests/test_m006_eventlog.py` with three async tests. All 3 pass in ~0.5 s with no external processes.

## Verification

pytest tests/test_m006_eventlog.py -v — 3 passed in 0.56s. All slice success criteria met: different session_ids route to different streams (R004); same capability routes to same stream (R005); append/read roundtrip confirmed (R003).

## Requirements Advanced

- R003 — EventLog Protocol + InProcessEventLog implemented; append/read roundtrip tested
- R004 — session_topic helper + test prove different session_ids go to different streams
- R005 — capability_topic helper + test prove same capability maps to same stream

## Requirements Validated

- R003 — test_r003_append_read_roundtrip passes — event appended to topic is readable back at offset
- R004 — test_r004_different_sessions_different_streams passes — session_topic("s1") != session_topic("s2")
- R005 — test_r005_same_capability_same_stream passes — capability_topic("search") returns the same stream for any session

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

None.

## Known Limitations

KafkaEventLog is a stub only — aiokafka is not installed and real broker integration is deferred to R017. Offset is a simple integer list index; no compaction or retention policy.

## Follow-ups

None.

## Files Created/Modified

- `src/mcp_agent_factory/streams/eventlog.py` — New file: EventLog Protocol, InProcessEventLog, session_topic, capability_topic
- `src/mcp_agent_factory/streams/kafka_adapter.py` — New file: KafkaEventLog stub with guarded aiokafka import
- `src/mcp_agent_factory/streams/__init__.py` — Export new symbols: EventLog, InProcessEventLog, session_topic, capability_topic, KafkaEventLog
- `tests/test_m006_eventlog.py` — New file: 3 async tests covering R003, R004, R005
