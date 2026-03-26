# S02: ReAct Loop — Perception, Reasoning, and Action

**Goal:** Implement a ReActAgent that wraps MCPOrchestrator and executes the full Perception→Reasoning→Action→Observation→Synthesis cycle, proven by unit and e2e pytest tests.
**Demo:** After this: pytest tests/test_react_loop.py tests/test_e2e_routing.py -v passes, showing a task routed through the full ReAct cycle with tool selection and execution visible in test output.

## Tasks
- [x] **T01: Created react_loop.py with ReActStep/ReActResult Pydantic v2 models and ReActAgent executing the full ReAct cycle over MCPOrchestrator** — Create `src/mcp_agent_factory/react_loop.py` with three classes: `ReActStep` (Pydantic BaseModel: type, content, tool_name, tool_args), `ReActResult` (Pydantic BaseModel: task, steps, answer, success), and `ReActAgent` (wraps an MCPOrchestrator instance).

ReActAgent.run(task: str) → ReActResult executes:
1. Perception: call self.orc.list_tools() → extract tool names
2. Reasoning: _select_tool(task, tool_names) — rule-based: contains 'echo' or quoted string → 'echo'; contains digits + add/sum/plus/+ → 'add'; else None. Append ReActStep(type='thought', ...)
3. Action: if tool selected, _extract_args(task, selected) → dict of args. Append ReActStep(type='action', tool_name=selected, tool_args=args, content=f'call {selected}'). Call self.orc.call_tool(selected, args).
4. Observation: extract text from result['content'][0]['text']. Append ReActStep(type='observation', content=obs). Set success = not result.get('isError', False).
5. If no tool: answer='No suitable tool found', success=False.

Arg extraction rules:
- echo: extract first quoted string (re.search(r'\"([^\"]+)\"', task)) or last word
- add: re.findall(r'[-+]?\d+\.?\d*', task) → first two numbers as a=float, b=float

Add `from __future__ import annotations` at top. Use Pydantic v2 (no @validator, use model_config or @field_validator if needed — not needed here since fields are plain types).
  - Estimate: 30m
  - Files: src/mcp_agent_factory/react_loop.py
  - Verify: python -c "from mcp_agent_factory.react_loop import ReActAgent, ReActResult, ReActStep; print('import ok')"
- [x] **T02: Created 7 unit tests with StubOrchestrator and 4 e2e tests via live MCPOrchestrator; all 23 suite tests pass** — Create two test files:

**tests/test_react_loop.py** — unit tests using a stub orchestrator (plain class, not Mock):

```python
class StubOrchestrator:
    def list_tools(self):
        return [{"name": "echo"}, {"name": "add"}]
    def call_tool(self, name, args):
        if name == "echo":
            return {"content": [{"text": args.get("message", "")}]}
        if name == "add":
            return {"content": [{"text": str(args["a"] + args["b"])}]}
        return {"isError": True, "content": [{"text": "unknown"}]}
```

Test cases (at minimum):
- test_echo_task: run('echo "hello"') → result.success=True, result.answer contains 'hello', steps has thought+action+observation
- test_add_task: run('add 3 and 5') → result.success=True, answer contains '8'
- test_no_tool: run('do something unrelated') → result.success=False, answer='No suitable tool found'
- test_steps_structure: verify steps list contains dicts/objects with type in {thought, action, observation}
- test_result_model: result is ReActResult instance, steps are ReActStep instances

**tests/test_e2e_routing.py** — integration tests using the `mcp_server` fixture from conftest.py:

```python
import pytest
from mcp_agent_factory.orchestrator import MCPOrchestrator
from mcp_agent_factory.react_loop import ReActAgent

def test_e2e_echo_routing(mcp_server):
    orc = MCPOrchestrator(mcp_server)
    orc.connect()
    agent = ReActAgent(orc)
    result = agent.run('echo "world"')
    assert result.success
    assert 'world' in result.answer
    orc.disconnect()

def test_e2e_add_routing(mcp_server):
    orc = MCPOrchestrator(mcp_server)
    orc.connect()
    agent = ReActAgent(orc)
    result = agent.run('add 10 and 20')
    assert result.success
    assert '30' in result.answer
    orc.disconnect()

def test_e2e_react_steps_present(mcp_server):
    orc = MCPOrchestrator(mcp_server)
    orc.connect()
    agent = ReActAgent(orc)
    result = agent.run('echo "test"')
    types = [s.type for s in result.steps]
    assert 'thought' in types
    assert 'action' in types
    assert 'observation' in types
    orc.disconnect()
```

The `mcp_server` fixture yields a subprocess.Popen — MCPOrchestrator accepts a Popen object. Check conftest.py to confirm the fixture signature and adapt if needed.
  - Estimate: 45m
  - Files: tests/test_react_loop.py, tests/test_e2e_routing.py
  - Verify: python -m pytest tests/test_react_loop.py tests/test_e2e_routing.py -v && python -m pytest tests/ -v
