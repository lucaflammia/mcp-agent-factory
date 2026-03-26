---
estimated_steps: 6
estimated_files: 3
skills_used: []
---

# T01: Create Pydantic models and PrivacyConfig

Create two pure Pydantic v2 modules with no external dependencies beyond pydantic.

Steps:
1. Create `src/mcp_agent_factory/models.py` — define `EchoInput(BaseModel)` with `message: str`, `EchoOutput(BaseModel)` with `text: str`, `AddInput(BaseModel)` with `a: float` and `b: float`, `AddOutput(BaseModel)` with `result: float`. Use standard Pydantic v2 `BaseModel` subclasses.
2. Create `src/mcp_agent_factory/config/__init__.py` — empty file to make config a Python package.
3. Create `src/mcp_agent_factory/config/privacy.py` — define `PrivacyConfig(BaseModel)` with `local_only: bool = True` and `allow_egress: bool = False`. Add `assert_no_egress(self) -> None` method that raises `RuntimeError('Egress is disabled by PrivacyConfig')` if `self.allow_egress is True`.
4. Verify imports work: `python -c "from mcp_agent_factory.models import EchoInput, AddInput; from mcp_agent_factory.config.privacy import PrivacyConfig; print('ok')"`

## Inputs

- ``src/mcp_agent_factory/__init__.py``

## Expected Output

- ``src/mcp_agent_factory/models.py``
- ``src/mcp_agent_factory/config/__init__.py``
- ``src/mcp_agent_factory/config/privacy.py``

## Verification

python -c "from mcp_agent_factory.models import EchoInput, AddInput, EchoOutput, AddOutput; from mcp_agent_factory.config.privacy import PrivacyConfig; print('ok')"
