# S02: ReAct Loop — Perception, Reasoning, and Action — UAT

**Milestone:** M001
**Written:** 2026-03-26T16:29:07.192Z

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: The slice deliverable is a Python module and test suite; pytest output is the authoritative proof of behaviour.

## Preconditions

- Python environment with mcp-agent-factory installed (`pip install -e .`)
- All S01 artifacts present (MCPOrchestrator, simulation server, conftest.py)
- Working directory: `/home/luca/Documents/Misc/mcp-agent-factory`

## Smoke Test

```
python -c "from mcp_agent_factory.react_loop import ReActAgent, ReActResult, ReActStep; print('import ok')"
```
Expected: prints `import ok`, exit 0.

## Test Cases

### 1. Unit: Echo task routes correctly

```
python -m pytest tests/test_react_loop.py::test_echo_task -v
```
1. StubOrchestrator returns echo and add tools from list_tools
2. Agent.run('echo "hello"') selects echo tool
3. **Expected:** result.success=True, 'hello' in result.answer, steps contain thought+action+observation

### 2. Unit: Add task routes and computes

```
python -m pytest tests/test_react_loop.py::test_add_task -v
```
1. Agent.run('add 3 and 5') selects add tool, extracts a=3.0, b=5.0
2. StubOrchestrator returns str(3.0+5.0) = '8.0'
3. **Expected:** result.success=True, '8' in result.answer

### 3. Unit: No-tool fallback

```
python -m pytest tests/test_react_loop.py::test_no_tool -v
```
1. Agent.run('do something unrelated') finds no matching tool
2. **Expected:** result.success=False, result.answer='No suitable tool found'

### 4. Unit: Steps structure

```
python -m pytest tests/test_react_loop.py::test_steps_structure -v
```
1. Run any task that selects a tool
2. **Expected:** result.steps is a list of ReActStep instances with .type in {thought, action, observation}

### 5. E2e: Echo routing over live MCP server

```
python -m pytest tests/test_e2e_routing.py::test_e2e_echo_routing -v
```
1. MCPOrchestrator() spawns simulation server subprocess
2. agent.run('echo "world"') routes through full ReAct cycle
3. **Expected:** result.success=True, 'world' in result.answer

### 6. E2e: Add routing over live MCP server

```
python -m pytest tests/test_e2e_routing.py::test_e2e_add_routing -v
```
1. agent.run('add 10 and 20') → selects add, sends a=10.0, b=20.0 to server
2. **Expected:** result.success=True, '30' in result.answer

### 7. E2e: ReAct steps present in trace

```
python -m pytest tests/test_e2e_routing.py::test_e2e_react_steps_present -v
```
1. agent.run('echo "test"') completes full cycle
2. **Expected:** result.steps contains thought, action, and observation step types

### 8. Full suite regression

```
python -m pytest tests/ -v
```
**Expected:** 23 passed, 0 failed, 0 errors.

## Edge Cases

### Large numbers in add task

```
python -m pytest tests/test_react_loop.py::test_add_large_numbers -v
```
1. run('add 1000000 and 2000000') → extracts floats correctly
2. **Expected:** answer contains '3000000'

### No-tool e2e graceful failure

```
python -m pytest tests/test_e2e_routing.py::test_e2e_no_tool_fails_gracefully -v
```
1. agent.run('do something unrelated') on live orchestrator
2. **Expected:** result.success=False, no exception raised

## Failure Signals

- ImportError on react_loop imports → T01 file missing or Pydantic version mismatch
- AssertionError in e2e tests → simulation server not starting; check S01 conftest and server script
- result.answer not containing expected string → _extract_args regex not matching task text

## Not Proven By This UAT

- LLM-based tool selection (rule-based only)
- Concurrent/parallel ReActAgent calls (single-outstanding-request limitation documented in KNOWLEDGE.md)
- Schema validation of tool arguments (deferred to S03)
- Privacy-first config (deferred to S03)

## Notes for Tester

E2e tests use MCPOrchestrator() with no arguments — the orchestrator spawns its own simulation server subprocess. They do NOT use the conftest mcp_server fixture. This is intentional and produces the same observable behaviour.
