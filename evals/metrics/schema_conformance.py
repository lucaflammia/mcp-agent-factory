"""Schema conformance metric for OrchestratorPlan outputs.

Validates that LLM-generated plans parse correctly against the Pydantic
contracts in src/mcp_agent_factory/orchestrator.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SchemaResult:
  """Result of schema conformance check."""
  valid: bool
  errors: list[str]

  def to_dict(self) -> dict:
    return {"valid": self.valid, "errors": self.errors}


def check_plan_conformance(raw_plan: dict[str, Any]) -> SchemaResult:
  """Validate a raw plan dict against OrchestratorPlan schema.

  Returns SchemaResult with validation errors if any.
  """
  from pydantic import ValidationError
  from mcp_agent_factory.orchestrator import OrchestratorPlan

  try:
    OrchestratorPlan.model_validate(raw_plan)
    return SchemaResult(valid=True, errors=[])
  except ValidationError as e:
    errors = [err["msg"] for err in e.errors()]
    return SchemaResult(valid=False, errors=errors)
  except Exception as e:
    return SchemaResult(valid=False, errors=[str(e)])


def check_graph_plan_conformance(raw_plan: dict[str, Any]) -> SchemaResult:
  """Validate a raw plan dict against ExecutionPlan schema (LangGraph path).

  Returns SchemaResult with validation errors if any.
  """
  from pydantic import ValidationError
  from mcp_agent_factory.graph_orchestrator import ExecutionPlan

  try:
    ExecutionPlan.model_validate(raw_plan)
    return SchemaResult(valid=True, errors=[])
  except ValidationError as e:
    errors = [err["msg"] for err in e.errors()]
    return SchemaResult(valid=False, errors=errors)
  except Exception as e:
    return SchemaResult(valid=False, errors=[str(e)])
