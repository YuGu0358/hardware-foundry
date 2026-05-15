"""EchoAgent — Phase 0 connectivity smoke test.

Takes the user's raw input, asks the cheap LLM (Claude Haiku via `agent:echo`)
to echo it back with a short prefix, and appends a Message to clarification
history. Proves FastAPI -> LangGraph -> BaseAgent -> LiteLLM -> Anthropic
works end-to-end.

It will be deleted once the real Clarifier agent lands in Phase 1.
"""

from __future__ import annotations

from typing import ClassVar

from foundry_agent_base import (
    AgentContext,
    BaseAgent,
    Message,
    MessageRole,
    ProductState,
    StateUpdate,
)


class EchoAgent(BaseAgent):
    name: ClassVar[str] = "echo"
    model: ClassVar[str] = "agent:echo"

    async def run(self, state: ProductState, ctx: AgentContext) -> StateUpdate:
        reply = await self.llm(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a connectivity test. Echo the user's message verbatim, "
                        "prefixed with 'ECHO: '. Do not add anything else."
                    ),
                },
                {"role": "user", "content": state.raw_input},
            ],
            temperature=0.0,
            max_tokens=200,
        )

        return {
            "clarification_history": [
                *state.clarification_history,
                Message(role=MessageRole.ASSISTANT, content=reply),
            ],
            "current_phase": "clarify",
        }
