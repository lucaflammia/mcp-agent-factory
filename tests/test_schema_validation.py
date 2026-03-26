"""
Schema validation and PrivacyConfig tests — Slice S03.

Proves that Pydantic v2 models gate tool arguments correctly and that
PrivacyConfig enforces local-only defaults.
"""
from __future__ import annotations

import pytest
from mcp_agent_factory.orchestrator import MCPOrchestrator
from mcp_agent_factory.config.privacy import PrivacyConfig


@pytest.fixture
def orc() -> MCPOrchestrator:
    with MCPOrchestrator() as o:
        yield o


# ---------------------------------------------------------------------------
# Schema validation — echo
# ---------------------------------------------------------------------------

class TestEchoValidation:
    def test_echo_missing_message(self, orc: MCPOrchestrator):
        result = orc.call_tool("echo", {})
        assert result["isError"] is True

    def test_echo_valid(self, orc: MCPOrchestrator):
        result = orc.call_tool("echo", {"message": "hi"})
        assert result["isError"] is False
        assert result["content"][0]["text"] == "hi"


# ---------------------------------------------------------------------------
# Schema validation — add
# ---------------------------------------------------------------------------

class TestAddValidation:
    def test_add_missing_field(self, orc: MCPOrchestrator):
        result = orc.call_tool("add", {"a": 1})
        assert result["isError"] is True

    def test_add_wrong_type(self, orc: MCPOrchestrator):
        # Pydantic v2 will reject a non-numeric string for a float field
        result = orc.call_tool("add", {"a": "notanumber", "b": 2})
        assert result["isError"] is True

    def test_add_valid(self, orc: MCPOrchestrator):
        result = orc.call_tool("add", {"a": 3, "b": 4})
        assert result["isError"] is False
        assert result["content"][0]["text"] == "7"


# ---------------------------------------------------------------------------
# PrivacyConfig
# ---------------------------------------------------------------------------

class TestPrivacyConfig:
    def test_privacy_config_defaults(self):
        cfg = PrivacyConfig()
        assert cfg.local_only is True
        assert cfg.allow_egress is False

    def test_assert_no_egress_passes_on_default(self):
        PrivacyConfig().assert_no_egress()  # must not raise

    def test_assert_no_egress_raises_when_enabled(self):
        with pytest.raises(RuntimeError):
            PrivacyConfig(allow_egress=True).assert_no_egress()
