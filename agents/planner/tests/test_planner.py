"""Phase 1 unit tests for PlannerAgent."""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from foundry_agent_base import (
    AgentContext,
    BaseAgent,
    Message,
    MessageRole,
    ProductSpec,
    ProductState,
    ReferenceProduct,
)
from foundry_agent_planner import PlannerAgent

_FIXED_USER_ID = UUID("00000000-0000-0000-0000-000000000010")
_FIXED_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000011")


def _valid_spec_payload() -> dict:
    """A plausible ProductSpec payload with 8 requirements and 3 markets."""
    requirements = [
        {
            "id": f"R{i:02d}",
            "statement": f"Functional requirement number {i}",
            "category": "functional",
            "priority": "must",
        }
        for i in range(1, 9)
    ]
    return {
        "title": "Smart Desk Lamp",
        "summary": "USB-C powered desk lamp with BLE app control.",
        "requirements": requirements,
        "constraints": {
            "max_dimensions_mm": [200.0, 200.0, 400.0],
            "max_weight_g": 800.0,
            "max_power_w": 12.0,
            "target_bom_cost_cents": 4500,
            "target_unit_count": 1000,
            "compliance_markets": ["CN", "EU", "US"],
        },
        "target_use_case": "office desk task lighting",
    }


@pytest.fixture
def mock_llm(monkeypatch):
    state: dict[str, str] = {"payload": ""}

    async def fake_llm(self, messages, **kw):
        return state["payload"]

    monkeypatch.setattr(BaseAgent, "llm", fake_llm)
    return state


def _make_state() -> ProductState:
    history = [
        Message(role=MessageRole.ASSISTANT, content="What power source?"),
        Message(role=MessageRole.USER, content="USB-C."),
    ]
    refs = [
        ReferenceProduct(
            name="BenQ ScreenBar Halo",
            url="https://example.com/benq-halo",
            summary="USB-powered monitor light with wireless controller.",
            design_takeaways=["asymmetric optics", "wireless puck control"],
            similarity_score=0.7,
        ),
        ReferenceProduct(
            name="Xiaomi Mi Smart LED Desk Lamp",
            url="https://example.com/xiaomi-lamp",
            summary="App-controlled desk lamp with 4 lighting scenes.",
            design_takeaways=["BLE pairing", "preset scenes"],
            similarity_score=0.6,
        ),
    ]
    return ProductState(
        user_id=_FIXED_USER_ID,
        project_id=_FIXED_PROJECT_ID,
        raw_input="smart desk lamp",
        clarification_history=history,
        reference_findings=refs,
    )


def _make_ctx() -> AgentContext:
    return AgentContext(
        run_id="run-planner",
        user_id=str(_FIXED_USER_ID),
        project_id=str(_FIXED_PROJECT_ID),
    )


@pytest.mark.phase1
async def test_planner_happy_path_produces_frozen_product_spec(mock_llm):
    # Arrange
    mock_llm["payload"] = json.dumps(_valid_spec_payload())

    # Act
    update = await PlannerAgent().run(_make_state(), _make_ctx())

    # Assert
    spec = update["product_spec"]
    assert isinstance(spec, ProductSpec)
    assert spec.frozen is True
    assert len(spec.requirements) >= 8  # noqa: PLR2004 — task spec requires ≥8
    assert set(spec.constraints.compliance_markets) == {"CN", "EU", "US"}
    assert update["current_phase"] == "plan"


@pytest.mark.phase1
async def test_planner_bad_json_raises_runtime_error(mock_llm):
    # Arrange
    mock_llm["payload"] = "{ this is not valid json"

    # Act / Assert
    with pytest.raises(RuntimeError, match="planner: failed to parse ProductSpec"):
        await PlannerAgent().run(_make_state(), _make_ctx())


@pytest.mark.phase1
async def test_planner_invalid_schema_raises_runtime_error(mock_llm):
    """ProductSpec validation failures (missing required field) must bubble up."""
    # Arrange — well-formed JSON but missing required `title`
    bad = _valid_spec_payload()
    del bad["title"]
    mock_llm["payload"] = json.dumps(bad)

    # Act / Assert
    with pytest.raises(RuntimeError, match="planner: failed to parse ProductSpec"):
        await PlannerAgent().run(_make_state(), _make_ctx())
