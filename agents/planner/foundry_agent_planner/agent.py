"""PlannerAgent — produces a frozen ProductSpec from clarified state."""

from __future__ import annotations

import json
from typing import ClassVar

from foundry_agent_base import (
    AgentContext,
    BaseAgent,
    Message,
    ProductSpec,
    ProductState,
    ReferenceProduct,
    StateUpdate,
)
from pydantic import ValidationError

from foundry_agent_planner.prompts import SYSTEM_PROMPT_V1, user_prompt


class PlannerAgent(BaseAgent):
    """Consumes raw_input + clarification_history + reference_findings → ProductSpec."""

    name: ClassVar[str] = "planner"
    # Claude Opus 4.5 via LiteLLM virtual name; see infra/litellm/config.yaml
    model: ClassVar[str] = "agent:planner"

    async def run(self, state: ProductState, ctx: AgentContext) -> StateUpdate:
        history_md = _render_history(state.clarification_history)
        references_md = _render_references(state.reference_findings or [])

        raw = await self.llm(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_V1},
                {
                    "role": "user",
                    "content": user_prompt(state.raw_input, history_md, references_md),
                },
            ],
            temperature=0.2,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )

        try:
            payload = json.loads(raw)
            spec = ProductSpec.model_validate({**payload, "frozen": True})
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(
                f"planner: failed to parse ProductSpec JSON ({exc}). Raw: {raw[:400]}"
            ) from exc

        return {
            "product_spec": spec,
            "current_phase": "plan",
        }


def _render_history(messages: list[Message]) -> str:
    if not messages:
        return ""
    lines: list[str] = []
    for m in messages:
        prefix = "USER" if m.role == "user" else "ASSISTANT"
        lines.append(f"[{prefix}] {m.content}")
    return "\n\n".join(lines)


def _render_references(refs: list[ReferenceProduct]) -> str:
    if not refs:
        return ""
    blocks: list[str] = []
    for r in refs:
        takeaways = "\n  - ".join(r.design_takeaways) if r.design_takeaways else "(none)"
        blocks.append(
            f"- {r.name} (similarity {r.similarity_score:.2f})\n"
            f"  URL: {r.url}\n"
            f"  {r.summary}\n"
            f"  Takeaways:\n  - {takeaways}"
        )
    return "\n".join(blocks)
