"""ComplianceAgent — selects applicable regulations for a frozen ProductSpec.

Phase 2 MVP: inline LLM knowledge only. A follow-up PR will replace the prompt's
inline rule catalogue with RAG over actual regulation corpora hosted in Qdrant.
"""

from __future__ import annotations

import json
from typing import ClassVar

import structlog
from foundry_agent_base import (
    AgentContext,
    BaseAgent,
    ComplianceReport,
    ComplianceTarget,
    ProductState,
    StateUpdate,
)
from pydantic import BaseModel, ValidationError

from foundry_agent_compliance.prompts import SYSTEM_PROMPT_V1, user_prompt

logger = structlog.get_logger()


class _ComplianceOutput(BaseModel):
    """Internal Pydantic envelope used to parse the LLM JSON response."""

    targets: list[ComplianceTarget]
    summary: str


class ComplianceAgent(BaseAgent):
    """Consumes ProductSpec → ComplianceReport listing applicable regulations."""

    name: ClassVar[str] = "compliance"
    model: ClassVar[str] = "agent:sonnet"

    async def run(self, state: ProductState, ctx: AgentContext) -> StateUpdate:
        if state.product_spec is None:
            logger.warning(
                "compliance.no_spec",
                run_id=ctx.run_id,
                project_id=ctx.project_id,
            )
            return {
                "compliance_report": ComplianceReport(
                    targets=[],
                    summary="No spec yet.",
                ),
            }

        spec_json = state.product_spec.model_dump_json(indent=2)
        markets = list(state.product_spec.constraints.compliance_markets)

        raw = await self.llm(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_V1},
                {"role": "user", "content": user_prompt(spec_json, markets)},
            ],
            temperature=0.2,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )

        try:
            payload = json.loads(raw)
            parsed = _ComplianceOutput.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(
                f"compliance: failed to parse ComplianceReport JSON ({exc}). "
                f"Raw: {raw[:400]}"
            ) from exc

        report = ComplianceReport(targets=parsed.targets, summary=parsed.summary)
        return {
            "compliance_report": report,
            "current_phase": "design",
        }
