"""
Unit tests for ReActAgent using a stub orchestrator (no subprocess).
"""
from __future__ import annotations

from mcp_agent_factory.react_loop import ReActAgent, ReActResult, ReActStep


class StubOrchestrator:
	def list_tools(self):
		return [{"name": "echo"}, {"name": "add"}]

	def call_tool(self, name, args):
		if name == "echo":
			return {"content": [{"text": args.get("message", "")}]}
		if name == "add":
			return {"content": [{"text": str(int(args["a"]) + int(args["b"]))}]}
		return {"isError": True, "content": [{"text": "unknown"}]}


def make_agent():
	return ReActAgent(StubOrchestrator())


def test_echo_task():
	agent = make_agent()
	result = agent.run('echo "hello"')
	assert result.success is True
	assert "hello" in result.answer
	types = [s.type for s in result.steps]
	assert "thought" in types
	assert "action" in types
	assert "observation" in types


def test_add_task():
	agent = make_agent()
	result = agent.run("add 3 and 5")
	assert result.success is True
	assert "8" in result.answer


def test_no_tool():
	agent = make_agent()
	result = agent.run("do something unrelated")
	assert result.success is False
	assert result.answer == "No suitable tool found"


def test_steps_structure():
	agent = make_agent()
	result = agent.run('echo "world"')
	valid_types = {"thought", "action", "observation"}
	for step in result.steps:
		assert step.type in valid_types


def test_result_model():
	agent = make_agent()
	result = agent.run('echo "test"')
	assert isinstance(result, ReActResult)
	for step in result.steps:
		assert isinstance(step, ReActStep)


def test_echo_extracts_message():
	agent = make_agent()
	result = agent.run('echo "goodbye"')
	assert "goodbye" in result.answer


def test_add_large_numbers():
	agent = make_agent()
	result = agent.run("add 100 and 200")
	assert result.success is True
	assert "300" in result.answer
