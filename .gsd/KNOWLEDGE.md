
## S03: Schema Validation and Privacy-First Config

### Catch both ValueError and ValidationError in _dispatch
`_dispatch`'s tools/call except clause must catch `(ValueError, ValidationError)` together. Pydantic v2 raises `ValidationError` (not `ValueError`) on bad input; the original handler only caught `ValueError`. Missing this means schema errors silently surface as uncaught exceptions rather than `isError=True` responses.

### AddInput uses float; format output as int string for whole numbers
`AddInput` fields are `float`. When the result is a whole number (e.g. 3+4=7.0), emit `"7"` not `"7.0"` — the existing lifecycle tests assert on `"7"`. Use `int(result)` formatting when result is integral.

### PrivacyConfig assert_no_egress raises on allow_egress=True, not allow_egress=False
`assert_no_egress()` raises `RuntimeError` only when `allow_egress is True`. The default (`allow_egress=False`) must pass silently. Tests verify both paths explicitly.

---

## S02: ReAct Loop — Perception, Reasoning, and Action

### mcp_server fixture yields MCPServerProcess, not raw Popen
`conftest.py`'s `mcp_server` fixture yields an `MCPServerProcess` wrapper object, not a `subprocess.Popen`. `MCPOrchestrator`'s constructor expects no argument (it spawns its own subprocess). E2e tests must use `MCPOrchestrator()` directly in a context manager rather than passing the fixture value — same observable behaviour, avoids constructor mismatch.

### StubOrchestrator pattern for ReActAgent unit tests
Use a plain Python class (not `unittest.mock.Mock`) implementing `list_tools()` and `call_tool()` as a stub. This avoids mock setup verbosity and makes test failures easy to read. The pattern is established in `tests/test_react_loop.py` and should be extended for any new tool added to the simulation server.

### Rule-based _select_tool is intentionally not LLM-backed
`ReActAgent._select_tool` uses regex heuristics (echo → quoted string or 'echo'; add → digits + arithmetic keyword). This is deterministic for testing. Any future LLM-based routing must be introduced as a separate strategy behind an interface — do not mutate the existing method or existing tests will break.

---

## S01: MCP Foundation — Server, Client, and Lifecycle

### setuptools build-backend on Python 3.11
`setuptools.backends.legacy:build` is not available on Python 3.11 hosts. Always use `setuptools.build_meta` as the build backend in `pyproject.toml`.

### Newline-delimited JSON over STDIO vs Content-Length framing
The simulation server uses newline-delimited JSON (one JSON object per line) rather than the HTTP-header-style Content-Length framing used by the official MCP spec. This works fine for subprocess testing but means the server is **not** wire-compatible with official MCP clients. S03 or a later slice should evaluate whether full spec framing is needed.

### MCPOrchestrator single-outstanding-request pattern
`_rpc()` assumes at most one in-flight request at a time. Concurrent `list_tools()` / `call_tool()` calls from multiple threads will corrupt the response stream. The current test suite is sequential so this is safe, but any future async or parallel test must be aware of this limitation.

### mcp_server fixture daemon thread
`tests/conftest.py` uses a daemon reader thread + queue for safe subprocess stdout consumption. Joining the subprocess with `proc.wait()` after tests can deadlock if the server doesn't exit cleanly. The fixture sends no explicit shutdown; it relies on the daemon thread being killed when the test process exits.

---

## M001 Completion: Cross-Cutting Lessons

### All requirements validated but gsd_requirement_update finds no rows
The GSD DB may not have been seeded with requirements from REQUIREMENTS.md if they were entered only as markdown. If requirement updates fail with "not found", update REQUIREMENTS.md manually and record the validation evidence there directly.

### git merge-base HEAD main returns empty when working directly on main
When auto-mode runs on the main branch (no integration branch), `git diff --stat HEAD $(git merge-base HEAD main)` returns empty. Use `git diff --stat $(git rev-list --max-parents=0 HEAD) HEAD` to diff from the root commit instead, which correctly surfaces all code changes.

### 31 tests across three layers confirm end-to-end coherence
The milestone's three slices exercise the same code path from different angles: lifecycle tests (raw STDIO protocol), ReAct unit tests (StubOrchestrator), ReAct e2e tests (live subprocess), and schema tests (validation edge cases). Running the full suite in one command (`pytest tests/ -v`) is sufficient to confirm all layers integrate.
