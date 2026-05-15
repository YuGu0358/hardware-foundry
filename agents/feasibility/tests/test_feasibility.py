"""Phase 2 unit tests for FeasibilityAgent."""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from foundry_agent_base import (
    AgentContext,
    BaseAgent,
    Constraints,
    FeasibilityReport,
    ProductSpec,
    ProductState,
    ReferenceProduct,
    Requirement,
)
from foundry_agent_feasibility import FeasibilityAgent

_FIXED_USER_ID = UUID("00000000-0000-0000-0000-000000000200")
_FIXED_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000201")


def _valid_feasibility_payload() -> dict:
    return {
        "bom_cost_band_cents": [1500, 2800],
        "schedule_weeks_band": [10, 14],
        "complexity_score": 6,
        "top_risks": [
            "Custom LED driver may need 2 board respins to hit flicker spec.",
            "EU RED radio certification adds ~6 weeks before shippable hardware.",
            "USB-C PD negotiation IC has 16-week lead time at >1k volumes.",
        ],
        "summary": "Feasible at $15-28 BOM over ~10-14 weeks; main risk is EU RED timeline.",
    }


def _make_spec() -> ProductSpec:
    requirements = [
        Requirement(
            id=f"R{i:02d}",
            statement=f"Functional requirement number {i}",
            category="functional",
            priority="must",
        )
        for i in range(1, 9)
    ]
    return ProductSpec(
        title="Smart Desk Lamp",
        summary="USB-C powered desk lamp with BLE app control.",
        requirements=requirements,
        constraints=Constraints(
            max_dimensions_mm=(200.0, 200.0, 400.0),
            max_weight_g=800.0,
            max_power_w=12.0,
            target_bom_cost_cents=4500,
            target_unit_count=1000,
            compliance_markets=["CN", "EU", "US"],
        ),
        target_use_case="office desk task lighting",
        frozen=True,
    )


def _make_state(spec: ProductSpec | None) -> ProductState:
    refs = [
        ReferenceProduct(
            name="BenQ ScreenBar Halo",
            url="https://example.com/benq-halo",
            summary="USB-powered monitor light with wireless controller.",
            design_takeaways=["asymmetric optics", "wireless puck control"],
            similarity_score=0.7,
        ),
    ]
    return ProductState(
        user_id=_FIXED_USER_ID,
        project_id=_FIXED_PROJECT_ID,
        raw_input="smart desk lamp",
        reference_findings=refs,
        product_spec=spec,
    )


def _make_ctx() -> AgentContext:
    return AgentContext(
        run_id="run-feasibility",
        user_id=str(_FIXED_USER_ID),
        project_id=str(_FIXED_PROJECT_ID),
    )


@pytest.fixture
def mock_llm(monkeypatch):
    state: dict[str, str] = {"payload": ""}

    async def fake_llm(self, messages, **kw):
        return state["payload"]

    monkeypatch.setattr(BaseAgent, "llm", fake_llm)
    return state


@pytest.mark.phase2
async def test_feasibility_happy_path_produces_report(mock_llm):
    # Arrange
    mock_llm["payload"] = json.dumps(_valid_feasibility_payload())

    # Act
    update = await FeasibilityAgent().run(_make_state(_make_spec()), _make_ctx())

    # Assert
    assert isinstance(update, dict)
    report = update["feasibility_report"]
    assert isinstance(report, FeasibilityReport)
    assert 1 <= report.complexity_score <= 10  # noqa: PLR2004 — schema bounds
    assert isinstance(report.bom_cost_band_cents, tuple)
    assert len(report.bom_cost_band_cents) == 2  # noqa: PLR2004 — 2-tuple band
    assert all(isinstance(v, int) for v in report.bom_cost_band_cents)
    assert isinstance(report.schedule_weeks_band, tuple)
    assert len(report.schedule_weeks_band) == 2  # noqa: PLR2004 — 2-tuple band
    assert all(isinstance(v, int) for v in report.schedule_weeks_band)
    assert 3 <= len(report.top_risks) <= 5  # noqa: PLR2004 — spec window
    assert update["current_phase"] == "design"


@pytest.mark.phase2
async def test_feasibility_no_spec_skips_llm(monkeypatch):
    # Arrange — LLM must NOT be called when product_spec is None
    async def boom_llm(self, messages, **kw):
        raise AssertionError("llm should not be called when product_spec is None")

    monkeypatch.setattr(BaseAgent, "llm", boom_llm)

    # Act
    update = await FeasibilityAgent().run(_make_state(spec=None), _make_ctx())

    # Assert
    assert update == {"feasibility_report": None}


@pytest.mark.phase2
async def test_feasibility_bad_json_raises_runtime_error(mock_llm):
    # Arrange
    mock_llm["payload"] = "{ this is not valid json"

    # Act / Assert
    with pytest.raises(RuntimeError, match=r"^feasibility: failed to parse"):
        await FeasibilityAgent().run(_make_state(_make_spec()), _make_ctx())
