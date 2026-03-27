"""PrivacyConfig — local-only defaults for MCP Agent Factory."""
from pydantic import BaseModel


class PrivacyConfig(BaseModel):
	local_only: bool = True
	allow_egress: bool = False

	def assert_no_egress(self) -> None:
		"""Raise RuntimeError if egress is enabled."""
		if self.allow_egress is True:
			raise RuntimeError("Egress is disabled by PrivacyConfig")
