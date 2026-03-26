"""
E2E routing tests — ReActAgent over a live MCPOrchestrator subprocess.

The mcp_server fixture from conftest.py yields an MCPServerProcess wrapper,
but MCPOrchestrator manages its own subprocess internally.  These tests
instantiate MCPOrchestrator() with no arguments so it spawns the server itself.
"""
from __future__ import annotations

import pytest

from mcp_agent_factory.orchestrator import MCPOrchestrator
from mcp_agent_factory.react_loop import ReActAgent


def test_e2e_echo_routing():
    with MCPOrchestrator() as orc:
        agent = ReActAgent(orc)
        result = agent.run('echo "world"')
    assert result.success
    assert "world" in result.answer


def test_e2e_add_routing():
    with MCPOrchestrator() as orc:
        agent = ReActAgent(orc)
        result = agent.run("add 10 and 20")
    assert result.success
    assert "30" in result.answer


def test_e2e_react_steps_present():
    with MCPOrchestrator() as orc:
        agent = ReActAgent(orc)
        result = agent.run('echo "test"')
    types = [s.type for s in result.steps]
    assert "thought" in types
    assert "action" in types
    assert "observation" in types


def test_e2e_no_tool_fails_gracefully():
    with MCPOrchestrator() as orc:
        agent = ReActAgent(orc)
        result = agent.run("do something unrelated")
    assert result.success is False
    assert result.answer == "No suitable tool found"
