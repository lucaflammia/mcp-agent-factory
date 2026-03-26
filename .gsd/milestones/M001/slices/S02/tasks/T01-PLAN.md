---
estimated_steps: 11
estimated_files: 1
skills_used: []
---

# T01: Implement ReActAgent with Pydantic models in react_loop.py

Create `src/mcp_agent_factory/react_loop.py` with three classes: `ReActStep` (Pydantic BaseModel: type, content, tool_name, tool_args), `ReActResult` (Pydantic BaseModel: task, steps, answer, success), and `ReActAgent` (wraps an MCPOrchestrator instance).

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

## Inputs

- ``src/mcp_agent_factory/orchestrator.py` — MCPOrchestrator API (list_tools, call_tool)`
- ``src/mcp_agent_factory/__init__.py` — package init`

## Expected Output

- ``src/mcp_agent_factory/react_loop.py` — ReActStep, ReActResult, ReActAgent with full run() logic`

## Verification

python -c "from mcp_agent_factory.react_loop import ReActAgent, ReActResult, ReActStep; print('import ok')"
