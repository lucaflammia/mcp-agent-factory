"""
Shared Pydantic v2 models and MCPContext for the multi-agent pipeline.

MCPContext is a lightweight observability primitive scoped to a single tool
call or agent step — mirrors the intent of the MCP SDK Context object.
It emits structured JSON log lines at DEBUG level, keeping observability
consistent with the M001/M002 logging conventions.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

class AgentTask(BaseModel):
	"""A unit of work routed through the multi-agent pipeline."""
	id: str = Field(default_factory=lambda: str(uuid.uuid4()))
	name: str
	payload: dict[str, Any] = Field(default_factory=dict)
	complexity: float = Field(default=0.5, ge=0.0, le=1.0)
	required_capability: str = "general"


class AnalysisResult(BaseModel):
	"""Structured output from AnalystAgent, persisted in Redis for handoff."""
	session_key: str
	metrics: dict[str, float] = Field(default_factory=dict)
	trends: list[str] = Field(default_factory=list)
	summary: str = ""


class ReportResult(BaseModel):
	"""Structured output from WriterAgent — the final pipeline artifact."""
	session_key: str
	report_text: str
	agent_trace: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# MCP Context primitive
# ---------------------------------------------------------------------------

@dataclass
class MCPContext:
	"""
	Lightweight observability context scoped to a single tool/agent step.

	Mirrors the MCP SDK Context object's intent:
	  - log()             → structured debug log line
	  - report_progress() → progress percentage + message

	Keeps a local trace list so callers can assert on what was logged.
	"""
	tool_name: str = "unknown"
	_trace: list[str] = field(default_factory=list, repr=False)

	def log(self, message: str) -> None:
		"""Emit a structured DEBUG log line and append to local trace."""
		entry = json.dumps({
			"event": "context_log",
			"tool": self.tool_name,
			"message": message,
		})
		logger.debug(entry)
		self._trace.append(message)

	def report_progress(self, pct: float, message: str) -> None:
		"""Emit a structured progress log line."""
		entry = json.dumps({
			"event": "context_progress",
			"tool": self.tool_name,
			"pct": round(pct, 2),
			"message": message,
		})
		logger.debug(entry)
		self._trace.append(f"[{int(pct * 100)}%] {message}")

	@property
	def trace(self) -> list[str]:
		return list(self._trace)
