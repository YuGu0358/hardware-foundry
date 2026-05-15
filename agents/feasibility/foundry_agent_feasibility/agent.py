"""FeasibilityAgent — rough cost / time / complexity / risk estimates.

Phase 2 MVP: LLM-only. No live supplier APIs (Octopart integration lands in
Phase 3 Component Selection). The agent reads the frozen ProductSpec plus any
reference products and compliance report already on state, then asks the LLM
to emit a FeasibilityReport with conservative, defensible bands.
"""

from __future__ import annotations

import json
from typing import ClassVar

import structlog
from foundry_agent_base import (
    AgentContext,
    BaseAgent,
    ComplianceReport,
    FeasibilityReport,
    ProductState,
    ReferenceProduct,
    StateUpdate,
)
from pydantic import BaseModel, Field, ValidationError

from foundry_agent_feasibility.prompts import SYSTEM_PROMPT_V1, user_prompt

logger = structlog.get_logger()


class _FeasibilityOutput(BaseModel):
    """Internal Pydantic envelope used to parse the LLM JSON response."""

    bom_cost_band_cents: tuple[int, int]
    schedule_weeks_band: tuple[int, int]
    complexity_score: int = Field(ge=1, le=10)
    top_risks: list[str] = Field(default_factory=list)
    summary: str


class FeasibilityAgent(BaseAgent):
    """Consumes ProductSpec (+ references + compliance) → FeasibilityReport."""

    name: ClassVar[str] = "feasibility"
    model: ClassVar[str] = "agent:sonnet"

    async def run(self, state: ProductState, ctx: AgentContext) -> StateUpdate:
        if state.product_spec is None:
            logger.warning(
                "feasibility.no_spec",
                run_id=ctx.run_id,
                project_id=ctx.project_id,
            )
            return {"feasibility_report": None}

        spec_json = state.product_spec.model_dump_json(indent=2)
        references_md = _render_references(state.reference_findings or [])
        compliance_md = _render_compliance(state.compliance_report)

        raw = await self.llm(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_V1},
                {
                    "role": "user",
                    "content": user_prompt(spec_json, references_md, compliance_md),
                },
            ],
            temperature=0.2,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )

        try:
            payload = json.loads(raw)
            parsed = _FeasibilityOutput.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(
                f"feasibility: failed to parse FeasibilityReport JSON ({exc}). "
                f"Raw: {raw[:400]}"
            ) from exc

        report = FeasibilityReport(
            bom_cost_band_cents=parsed.bom_cost_band_cents,
            schedule_weeks_band=parsed.schedule_weeks_band,
            complexity_score=parsed.complexity_score,
            top_risks=parsed.top_risks,
            summary=parsed.summary,
        )
        return {
            "feasibility_report": report,
            "current_phase": "design",
        }


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


def _render_compliance(report: ComplianceReport | None) -> str:
    if report is None or not report.targets:
        return ""
    lines = [f"Summary: {report.summary}", "Targets:"]
    for t in report.targets:
        clause = f" ({t.clause_ref})" if t.clause_ref else ""
        lines.append(
            f"- [{t.severity}] {t.market} — {t.regulation}{clause}: {t.applies_because}"
        )
    return "\n".join(lines)
