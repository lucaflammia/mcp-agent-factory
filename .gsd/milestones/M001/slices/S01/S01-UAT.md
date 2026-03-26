# S01: MCP Foundation — Server, Client, and Lifecycle — UAT

**Milestone:** M001
**Written:** 2026-03-26T16:23:02.566Z

# S01: MCP Foundation — Server, Client, and Lifecycle — UAT

**Milestone:** M001
**Written:** 2026-03-26

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: The slice deliverable is a subprocess-based protocol implementation. The pytest suite exercises the full protocol over a live server subprocess — this is equivalent to a live-runtime test and produces deterministic, repeatable evidence.

## Preconditions

1. Python 3.11+ available
2. Package installed in editable mode: `pip install -e ".[dev]"` from project root
3. Working directory is `/home/luca/Documents/Misc/mcp-agent-factory`

## Smoke Test

```
python -m pytest tests/test_mcp_lifecycle.py -v
```
Expected: `12 passed` in under 10 seconds. Any failure is a blocker.

## Test Cases

### 1. MCP Initialize Handshake

1. Run: `python -m pytest tests/test_mcp_lifecycle.py::TestInitialize -v`
2. Observe that `test_initialize_returns_protocol_version`, `test_initialize_server_info`, `test_initialize_capabilities_present` all PASS
3. **Expected:** Server responds with `protocolVersion`, `serverInfo.name == "mcp-simulation-server"`, and a `capabilities` dict containing `tools`.

### 2. Tool Discovery (tools/list)

1. Run: `python -m pytest tests/test_mcp_lifecycle.py::TestListTools -v`
2. Observe all 4 tests PASS
3. **Expected:** `tools/list` returns a list with at least 2 entries; entries named `echo` and `add` are both present; each tool has `name`, `description`, and `inputSchema` fields.

### 3. Tool Invocation (tools/call)

1. Run: `python -m pytest tests/test_mcp_lifecycle.py::TestCallTool -v`
2. Observe all 5 tests PASS
3. **Expected:**
   - `echo` tool returns the input message back in content
   - `add` tool returns the numeric sum
   - Calling an unknown tool returns `isError: true`
   - `echo` with empty string returns empty content
   - `add` with negative numbers returns correct signed result

### 4. Raw STDIO Protocol Verification

1. Run:
   ```
   echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python -m mcp_agent_factory.server 2>/dev/null
   ```
2. **Expected:** stdout contains a single JSON line with `"result"` key containing `"protocolVersion"`.

### 5. Server Import Sanity

1. Run: `python -c "import mcp_agent_factory.server; import mcp_agent_factory.orchestrator; print('OK')"`
2. **Expected:** prints `OK` with exit code 0.

## Edge Cases

### Unknown Tool Error Shape

1. Run: `python -m pytest tests/test_mcp_lifecycle.py::TestCallTool::test_call_unknown_tool_returns_is_error -v`
2. **Expected:** Response has `isError: true` — confirms the orchestrator surfaces tool errors without raising Python exceptions.

### Negative Number Addition

1. Run: `python -m pytest tests/test_mcp_lifecycle.py::TestCallTool::test_call_add_negative_numbers -v`
2. **Expected:** `add(-3, 7)` returns `4` — confirms numeric parsing handles negative inputs.

## Failure Signals

- Any test in `TestInitialize` failing → initialize handshake broken; check server stdout framing
- `test_list_tools_schema_shape` failing → tool schema format changed; check server.py tools definition
- `test_call_echo` or `test_call_add` failing → tools/call dispatch broken; check orchestrator._rpc() response parsing
- Import error on `mcp_agent_factory.server` → build backend or package install issue; re-run `pip install -e ".[dev]"`

## Not Proven By This UAT

- Wire compatibility with official MCP clients (Content-Length framing not implemented)
- Concurrent tool calls (single-outstanding-request pattern; no parallel safety)
- Server behavior under malformed JSON input
- ReAct loop or schema validation (S02, S03)

## Notes for Tester

The server uses newline-delimited JSON, not the Content-Length framing of the official MCP spec. This is intentional for this slice — do not test with an official MCP client. The `mcp_server` pytest fixture spawns a fresh server subprocess per test class, so individual test isolation is strong. If tests hang, check for subprocess leaks (daemon thread should prevent this but a `proc.kill()` fallback in conftest covers most cases).

