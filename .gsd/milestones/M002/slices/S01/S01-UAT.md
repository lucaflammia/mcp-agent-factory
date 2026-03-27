# S01: Async TaskScheduler — UAT

**Milestone:** M002
**Written:** 2026-03-27T08:01:55.876Z

## UAT: Async TaskScheduler\n\n### Smoke Test\n\n```python\nimport asyncio\nfrom mcp_agent_factory.scheduler import TaskScheduler, TaskItem\n\nasync def handler(task):\n    print(f\"Handled: {task.name} (priority={task.priority})\")\n\nasync def main():\n    s = TaskScheduler()\n    await s._inbox.put(TaskItem(name=\"low\", priority=1))\n    await s._inbox.put(TaskItem(name=\"high\", priority=10))\n    await s._inbox.put(TaskItem(name=\"mid\", priority=5))\n    try:\n        await asyncio.wait_for(s.run(handler), timeout=0.5)\n    except asyncio.TimeoutError:\n        pass\n\nasyncio.run(main())\n```\n\nExpected output (high → mid → low).
