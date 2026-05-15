"""ComponentSelectionAgent — Phase 3 slice 2.

The agent now uses an LLM-driven ComponentQuery extractor: it consumes the
frozen ProductSpec (plus any ReferenceProduct findings) and asks the LLM to
emit a structured list of ComponentQuery objects covering the major
subsystems (compute, power, sensors, outputs, connectors). Each query is
then handed to the injected SupplierAdapter (StubSupplierAdapter in CI /
dev). Real Digi-Key / LCSC / Octopart adapters land in slices 3-5.
"""

from __future__ import annotations

import json
from typing import ClassVar

import structlog
from foundry_agent_base import (
    BOM,
    AgentContext,
    BaseAgent,
    BOMItem,
    ComponentQuery,
    ProductSpec,
    ProductState,
    ReferenceProduct,
    StateUpdate,
)
from pydantic import BaseModel, Field, ValidationError

from foundry_agent_component_selection.prompts import (
    EXTRACTION_SYSTEM_PROMPT_V1,
    extraction_user_prompt,
)
from foundry_agent_component_selection.suppliers import (
    StubSupplierAdapter,
    SupplierAdapter,
)

logger = structlog.get_logger()

_PRODUCTION_SUPPLIERS = {"digikey", "lcsc", "octopart", "jlcpcb"}


class _ExtractorOutput(BaseModel):
    """Internal Pydantic envelope used to parse the extractor LLM JSON response."""

    queries: list[ComponentQuery]
    summary: str = Field(default="")


class ComponentSelectionAgent(BaseAgent):
    """Consumes ProductSpec → BOM via the configured SupplierAdapter."""

    name: ClassVar[str] = "component_selection"
    model: ClassVar[str] = "agent:sonnet"

    def __init__(self, adapter: SupplierAdapter | None = None) -> None:
        super().__init__()
        self._adapter: SupplierAdapter = adapter or StubSupplierAdapter()

    async def run(self, state: ProductState, ctx: AgentContext) -> StateUpdate:
        if state.product_spec is None:
            logger.warning(
                "component_selection.no_spec",
                run_id=ctx.run_id,
                project_id=ctx.project_id,
            )
            return {"bom": None}

        queries = await self._extract_queries(
            state.product_spec,
            state.reference_findings or [],
        )

        items: list[BOMItem] = []
        for q in queries:
            matches = await self._adapter.search(q)
            if not matches:
                continue
            best = max(matches, key=lambda m: m.score)
            # Map non-production sentinels (e.g. "stub") to "other" so BOMItem
            # stays on its production Literal. Stub-sourced rows remain
            # identifiable via mpn starting with "STUB-".
            supplier = (
                best.supplier if best.supplier in _PRODUCTION_SUPPLIERS else "other"
            )
            items.append(
                BOMItem(
                    mpn=best.mpn,
                    manufacturer=best.manufacturer,
                    description=best.description,
                    quantity=q.quantity,
                    unit_price_cents=best.unit_price_cents,
                    supplier=supplier,
                    supplier_part_number=best.supplier_part_number,
                    in_stock=best.in_stock,
                    datasheet_url=best.datasheet_url,
                    alternatives=[m.mpn for m in matches if m.mpn != best.mpn],
                )
            )

        total = sum(it.unit_price_cents * it.quantity for it in items)
        return {
            "bom": BOM(items=items, total_cost_cents=total, currency="CNY"),
            "current_phase": "design",
        }

    async def _extract_queries(
        self,
        spec: ProductSpec,
        references: list[ReferenceProduct],
    ) -> list[ComponentQuery]:
        raw = await self.llm(
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT_V1},
                {
                    "role": "user",
                    "content": extraction_user_prompt(spec, references),
                },
            ],
            temperature=0.2,
            max_tokens=3000,
            response_format={"type": "json_object"},
        )
        try:
            parsed = _ExtractorOutput.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(
                f"component_selection: failed to parse extractor JSON ({exc}). "
                f"Raw: {raw[:400]}"
            ) from exc
        return parsed.queries
