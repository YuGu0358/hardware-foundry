"""ClarifierAgent — Phase 1 single-shot disambiguation."""

from __future__ import annotations

import json
from typing import ClassVar

from foundry_agent_base import (
    AgentContext,
    BaseAgent,
    Message,
    MessageRole,
    ProductState,
    StateUpdate,
)
from pydantic import BaseModel, Field, ValidationError

from foundry_agent_clarifier.prompts import SYSTEM_PROMPT_V1, user_prompt_v1


class ClarificationQuestion(BaseModel):
    """One disambiguation question."""

    id: str
    topic: str
    question: str
    sample_options: list[str] = Field(default_factory=list)
    rationale: str | None = None


class ClarifierOutput(BaseModel):
    """Structured Clarifier response (parsed from LLM JSON)."""

    questions: list[ClarificationQuestion]
    summary: str = ""


class ClarifierAgent(BaseAgent):
    """Asks the user 4-6 targeted disambiguation questions.

    Phase 1 single-shot: emits one round of questions and returns. The user is
    expected to reply via a follow-up message; subsequent rounds (and a real
    convergence check) ship in a later PR alongside LangGraph interrupt flow.
    """

    name: ClassVar[str] = "clarifier"
    model: ClassVar[str] = "agent:sonnet"

    async def run(self, state: ProductState, ctx: AgentContext) -> StateUpdate:
        raw = await self.llm(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_V1},
                {"role": "user", "content": user_prompt_v1(state.raw_input)},
            ],
            temperature=0.3,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )

        try:
            parsed = ClarifierOutput.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(
                f"clarifier: failed to parse LLM JSON ({exc}). Raw: {raw[:300]}"
            ) from exc

        message_md = _render_questions_markdown(parsed)
        new_message = Message(role=MessageRole.ASSISTANT, content=message_md)

        return {
            "clarification_history": [*state.clarification_history, new_message],
            "current_phase": "clarify",
        }


def _render_questions_markdown(out: ClarifierOutput) -> str:
    """Turn structured questions into a human-readable Markdown message."""
    lines: list[str] = []
    if out.summary:
        lines.append(f"_{out.summary}_\n")
    for q in out.questions:
        lines.append(f"**{q.id}. ({q.topic}) {q.question}**")
        if q.sample_options:
            for opt in q.sample_options:
                lines.append(f"  - {opt}")
        if q.rationale:
            lines.append(f"  > _{q.rationale}_")
        lines.append("")
    return "\n".join(lines).rstrip()
