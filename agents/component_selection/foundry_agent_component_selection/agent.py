"""ComponentSelectionAgent — Phase 3 foundation slice.

Uses StubSupplierAdapter to demonstrate end-to-end flow. Real adapter
routing + Agentic RAG lands in follow-up PRs.
"""

from __future__ import annotations

from typing import ClassVar

import structlog
from foundry_agent_base import (
    BOM,
    AgentContext,
    BaseAgent,
    BOMItem,
    ComponentQuery,
    ProductState,
    Requirement,
    StateUpdate,
)

from foundry_agent_component_selection.suppliers import (
    StubSupplierAdapter,
    SupplierAdapter,
)

logger = structlog.get_logger()


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

        # Phase 3 slice 1 — deterministic skeleton:
        # For each Requirement with category="functional", emit one ComponentQuery
        # built from the requirement statement. Hit the stub adapter, take the
        # top-scored match per query. Assemble into BOM.
        queries = [
            _query_from_requirement(r)
            for r in state.product_spec.requirements
            if r.category == "functional"
        ]
        items: list[BOMItem] = []
        for q in queries:
            matches = await self._adapter.search(q)
            if not matches:
                continue
            best = max(matches, key=lambda m: m.score)
            items.append(
                BOMItem(
                    mpn=best.mpn,
                    manufacturer=best.manufacturer,
                    description=best.description,
                    quantity=q.quantity,
                    unit_price_cents=best.unit_price_cents,
                    supplier=best.supplier,
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


def _query_from_requirement(req: Requirement) -> ComponentQuery:
    """Heuristic stub — slice 2 will replace with an LLM-driven parameter extractor."""
    return ComponentQuery(role=req.id, parameters={"statement": req.statement})
