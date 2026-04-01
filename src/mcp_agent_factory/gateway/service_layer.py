"""InternalServiceLayer — routes tool calls to their implementations."""
from __future__ import annotations

from typing import Any

from mcp_agent_factory.agents.models import AgentTask, MCPContext
from mcp_agent_factory.agents.pipeline_orchestrator import MultiAgentOrchestrator
from mcp_agent_factory.knowledge import query_knowledge_base
from mcp_agent_factory.messaging.bus import AgentMessage, MessageBus
from mcp_agent_factory.models import AddInput
from mcp_agent_factory.session.manager import RedisSessionManager

from .sampling import SamplingHandler
from .validation import ValidationGate


class InternalServiceLayer:
    """Handles tool dispatch, delegating validation to ValidationGate.

    ``handle`` mirrors the ``if tool_name == ...`` block that previously
    lived inside ``_mcp_dispatch``.  It raises ``ValidationError`` (from
    pydantic) or ``ValueError`` so the thin dispatcher in app.py can turn
    those into structured MCP error responses without any tool-specific logic.
    """

    def __init__(
        self,
        bus: MessageBus,
        session: RedisSessionManager,
        sampling_handler: SamplingHandler,
        vector_store: Any,
        embedder: Any,
    ) -> None:
        self._bus = bus
        self._session = session
        self._sampling_handler = sampling_handler
        self._vector_store = vector_store
        self._embedder = embedder
        self._gate = ValidationGate()

    async def handle(
        self,
        tool_name: str,
        args: dict[str, Any],
        claims: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Dispatch *tool_name* with *args* and return a result dict.

        Raises:
            pydantic.ValidationError: when tool arguments fail schema validation.
            ValueError: when *tool_name* is not recognised.
        """
        if tool_name == "echo":
            text = args.get("text", "")
            return {"content": [{"type": "text", "text": text}]}

        if tool_name == "add":
            inp = self._gate.validate(AddInput, args)  # raises ValidationError on bad input
            result = inp.a + inp.b
            text = str(int(result)) if result == int(result) else str(result)
            return {"content": [{"type": "text", "text": text}]}

        if tool_name == "analyse_and_report":
            task = AgentTask(
                task_id=str(args.get("task_id", "gw")),
                description=args.get("description", ""),
                context=args.get("context", {}),
            )
            ctx = MCPContext(session_id=str(args.get("task_id", "gw")))
            orchestrator = MultiAgentOrchestrator(self._session)
            report = await orchestrator.run_pipeline(task, ctx)
            return {"content": [{"type": "text", "text": report.summary}]}

        if tool_name == "sampling_demo":
            prompt = args.get("prompt", "")
            result = await self._sampling_handler.handle(prompt)
            return {"content": [{"type": "text", "text": result.completion}]}

        if tool_name == "query_knowledge_base":
            owner_id = claims["sub"] if claims else "dev"
            chunks = query_knowledge_base(
                args.get("query", ""),
                owner_id,
                self._vector_store,
                self._embedder,
                args.get("top_k", 5),
            )
            self._bus.publish(
                "knowledge.retrieved",
                AgentMessage(
                    topic="knowledge.retrieved",
                    sender="gateway",
                    recipient="*",
                    content={
                        "owner_id": owner_id,
                        "chunk_count": len(chunks),
                        "source": "vector_store",
                    },
                ),
            )
            return {"content": [{"type": "text", "text": str(chunks)}]}

        raise ValueError(f"Unknown tool: {tool_name}")
