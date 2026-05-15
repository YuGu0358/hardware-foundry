"""Phase 3 slice 1 unit tests for ComponentSelectionAgent + StubSupplierAdapter."""

from __future__ import annotations

from uuid import UUID

import pytest
from foundry_agent_base import (
    BOM,
    AgentContext,
    ComponentQuery,
    Constraints,
    ProductSpec,
    ProductState,
    Requirement,
)
from foundry_agent_component_selection import (
    ComponentSelectionAgent,
    StubSupplierAdapter,
)

_FIXED_USER_ID = UUID("00000000-0000-0000-0000-000000000300")
_FIXED_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000301")
_EXPECTED_MATCH_COUNT = 3
_EXPECTED_SCORES = [0.9, 0.7, 0.5]


def _make_ctx() -> AgentContext:
    return AgentContext(
        run_id="run-component-selection",
        user_id=str(_FIXED_USER_ID),
        project_id=str(_FIXED_PROJECT_ID),
    )


def _make_state(spec: ProductSpec | None) -> ProductState:
    return ProductState(
        user_id=_FIXED_USER_ID,
        project_id=_FIXED_PROJECT_ID,
        raw_input="smart desk lamp",
        product_spec=spec,
    )


def _make_spec_with_mix() -> ProductSpec:
    requirements = [
        Requirement(id="R01", statement="Drive a 12 W LED panel", category="functional"),
        Requirement(id="R02", statement="USB-C PD input", category="functional"),
        Requirement(id="R03", statement="BLE app control", category="functional"),
        Requirement(id="R04", statement="Max 200 mm tall", category="constraint"),
        Requirement(id="R05", statement="Quiet operation", category="preference"),
        Requirement(id="R06", statement="No exposed mains", category="safety"),
    ]
    return ProductSpec(
        title="Smart Desk Lamp",
        summary="USB-C powered desk lamp with BLE app control.",
        requirements=requirements,
        constraints=Constraints(target_unit_count=1000, compliance_markets=["CN"]),
        target_use_case="office desk task lighting",
        frozen=True,
    )


@pytest.mark.phase3
async def test_stub_adapter_returns_three_distinct_matches():
    # Arrange
    adapter = StubSupplierAdapter()
    query = ComponentQuery(role="led_driver", parameters={"current_ma": 700})

    # Act
    matches = await adapter.search(query)

    # Assert
    assert len(matches) == _EXPECTED_MATCH_COUNT
    mpns = [m.mpn for m in matches]
    assert len(set(mpns)) == _EXPECTED_MATCH_COUNT  # all distinct
    assert all(m.supplier == "stub" for m in matches)
    assert [m.score for m in matches] == _EXPECTED_SCORES
    prices = [m.unit_price_cents for m in matches]
    assert len(set(prices)) == _EXPECTED_MATCH_COUNT  # all distinct


@pytest.mark.phase3
async def test_stub_adapter_handles_empty_parameters():
    # Arrange
    adapter = StubSupplierAdapter()
    query = ComponentQuery(role="usb_c_connector")  # parameters defaults to {}

    # Act
    matches = await adapter.search(query)

    # Assert
    assert len(matches) == _EXPECTED_MATCH_COUNT
    assert all(m.supplier == "stub" for m in matches)
    assert all(m.parametric == {} for m in matches)


@pytest.mark.phase3
async def test_component_selection_agent_with_spec_emits_bom():
    # Arrange
    spec = _make_spec_with_mix()
    functional_count = sum(1 for r in spec.requirements if r.category == "functional")
    assert functional_count == _EXPECTED_MATCH_COUNT  # sanity: 3 functional requirements
    agent = ComponentSelectionAgent(adapter=StubSupplierAdapter())

    # Act
    update = await agent.run(_make_state(spec), _make_ctx())

    # Assert
    assert isinstance(update, dict)
    assert update["current_phase"] == "design"
    bom = update["bom"]
    assert isinstance(bom, BOM)
    assert len(bom.items) == functional_count  # one per functional requirement
    for item in bom.items:
        assert item.supplier == "stub"
        # Stub returns 3 candidates; the chosen mpn is excluded from alternatives,
        # leaving 2 alternates per item.
        assert len(item.alternatives) == _EXPECTED_MATCH_COUNT - 1
    expected_total = sum(it.unit_price_cents * it.quantity for it in bom.items)
    assert bom.total_cost_cents == expected_total


@pytest.mark.phase3
async def test_component_selection_agent_no_spec_returns_empty_bom():
    # Arrange
    agent = ComponentSelectionAgent(adapter=StubSupplierAdapter())

    # Act
    update = await agent.run(_make_state(spec=None), _make_ctx())

    # Assert
    assert update == {"bom": None}
