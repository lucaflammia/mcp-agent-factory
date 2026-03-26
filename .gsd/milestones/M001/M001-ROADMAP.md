# M001: 

## Vision
Establish a working multi-agent orchestration engine over MCP that demonstrates the full Perception→Reasoning→Action cycle, with schema-validated tool calls and privacy-first defaults — proving that the Fargin Curriculum's theory maps directly to executable, testable code.

## Slice Overview
| ID | Slice | Risk | Depends | Done | After this |
|----|-------|------|---------|------|------------|
| S01 | MCP Foundation — Server, Client, and Lifecycle | high | — | ✅ | pytest tests/test_mcp_lifecycle.py -v passes, showing the orchestrator listing and calling tools on a live simulation server subprocess over STDIO. |
| S02 | ReAct Loop — Perception, Reasoning, and Action | medium | S01 | ✅ | pytest tests/test_react_loop.py tests/test_e2e_routing.py -v passes, showing a task routed through the full ReAct cycle with tool selection and execution visible in test output. |
| S03 | Schema Validation and Privacy-First Config | low | S01 | ✅ | pytest tests/ -v passes in full, including schema rejection and privacy flag tests. |
