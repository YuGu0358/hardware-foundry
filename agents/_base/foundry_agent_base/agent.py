"""BaseAgent — abstract foundation every Hardware Foundry agent extends.

Wraps three cross-cutting concerns so individual agents stay focused on logic:

1. **LLM access** via LiteLLM gateway (model selection by virtual name).
2. **Observability** — every `run()` is auto-traced via Langfuse.
3. **State discipline** — agents return `StateUpdate` (partial dict),
   never mutate `ProductState` directly.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

import structlog
from langfuse import Langfuse
from litellm import acompletion

from foundry_agent_base.state import ProductState

logger = structlog.get_logger()


# A StateUpdate is whatever subset of ProductState fields the agent wants
# LangGraph to merge into the running state.
StateUpdate = dict[str, Any]


@dataclass(frozen=True)
class AgentContext:
    """Per-run context injected into BaseAgent.run() by the orchestrator."""

    run_id: str
    user_id: str
    project_id: str
    trace_id: str | None = None


class BaseAgent(ABC):
    """Abstract base for every agent in the Hardware Foundry graph.

    Subclasses MUST:
      - set `name` (class var)
      - implement `run(state, ctx) -> StateUpdate`

    Subclasses SHOULD:
      - import their prompt template from a sibling `prompts/v{N}.md` file
      - call `self.llm(...)` for LLM calls so token usage is tracked
    """

    name: ClassVar[str] = "base"
    model: ClassVar[str] = "agent:sonnet"

    def __init__(self) -> None:
        self._litellm_url = os.environ.get("LITELLM_URL", "http://localhost:4000")
        self._litellm_key = os.environ.get("LITELLM_MASTER_KEY", "sk-litellm-master-dev")
        self._langfuse = self._init_langfuse()

    @staticmethod
    def _init_langfuse() -> Langfuse | None:
        pk = os.environ.get("LANGFUSE_PUBLIC_KEY")
        sk = os.environ.get("LANGFUSE_SECRET_KEY")
        host = os.environ.get("LANGFUSE_HOST", "http://localhost:3001")
        if not pk or not sk:
            return None
        return Langfuse(public_key=pk, secret_key=sk, host=host)

    @abstractmethod
    async def run(self, state: ProductState, ctx: AgentContext) -> StateUpdate:
        """Process the state and return a partial update.

        DO NOT mutate `state`. Return only the fields you changed.
        """
        raise NotImplementedError

    async def llm(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Send messages through the LiteLLM gateway. Returns the text content."""
        params: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "api_base": self._litellm_url,
            "api_key": self._litellm_key,
        }
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if response_format is not None:
            params["response_format"] = response_format

        resp = await acompletion(**params)
        content = resp.choices[0].message.content
        if content is None:
            raise RuntimeError(f"{self.name}: LLM returned no content")
        return content

    async def __call__(self, state: ProductState, ctx: AgentContext) -> StateUpdate:
        """Thin wrapper that adds structured logging + Langfuse span."""
        log = logger.bind(agent=self.name, run_id=ctx.run_id, phase=state.current_phase)
        log.info("agent.start")
        span = None
        if self._langfuse and ctx.trace_id:
            span = self._langfuse.span(
                trace_id=ctx.trace_id,
                name=f"agent:{self.name}",
                input=state.model_dump(mode="json"),
            )
        try:
            update = await self.run(state, ctx)
            log.info("agent.done", update_keys=list(update.keys()))
            if span:
                span.end(output=update)
            return update
        except Exception as exc:
            log.exception("agent.failed", error=str(exc))
            if span:
                span.end(level="ERROR", status_message=str(exc))
            raise
