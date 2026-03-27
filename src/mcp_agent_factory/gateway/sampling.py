"""
Sampling / createMessage handler for the MCP API Gateway.

Provides a simple protocol + stub implementation so the gateway can serve
POST /sampling without a real LLM connection during development/testing.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class SamplingResult(BaseModel):
    prompt: str
    completion: str
    model: str = "stub"


@runtime_checkable
class SamplingClient(Protocol):
    async def request_completion(self, prompt: str) -> SamplingResult:
        ...


class StubSamplingClient:
    """Returns a deterministic stub completion — no LLM required."""

    async def request_completion(self, prompt: str) -> SamplingResult:
        return SamplingResult(prompt=prompt, completion="[stub] " + prompt[:50])


class SamplingHandler:
    def __init__(self, client: SamplingClient | None = None) -> None:
        self._client: SamplingClient = client or StubSamplingClient()

    def set_client(self, client: SamplingClient) -> None:
        self._client = client

    async def handle(self, prompt: str) -> SamplingResult:
        return await self._client.request_completion(prompt)
