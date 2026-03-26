---
estimated_steps: 52
estimated_files: 2
skills_used: []
---

# T02: Write unit tests (stub orchestrator) and e2e routing tests (live subprocess)

Create two test files:

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

## Inputs

- ``src/mcp_agent_factory/react_loop.py` — ReActAgent implementation from T01`
- ``src/mcp_agent_factory/orchestrator.py` — MCPOrchestrator for e2e tests`
- ``tests/conftest.py` — mcp_server fixture`

## Expected Output

- ``tests/test_react_loop.py` — unit tests with stub orchestrator (≥5 test cases)`
- ``tests/test_e2e_routing.py` — e2e integration tests against live subprocess (≥3 test cases)`

## Verification

python -m pytest tests/test_react_loop.py tests/test_e2e_routing.py -v && python -m pytest tests/ -v
