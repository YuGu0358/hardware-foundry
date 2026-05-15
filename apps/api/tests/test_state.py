"""Phase 1 unit tests for ProductState and its sub-schemas.

Verifies default values, required fields, and round-trip serialization for the
contracts that Phase 1+ agents depend on.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from foundry_agent_base import (
    Constraints,
    EnclosurePCBContract,
    Hole,
    ProductSpec,
    ProductState,
    Requirement,
)
from pydantic import ValidationError

_FIXED_USER_ID = UUID("00000000-0000-0000-0000-000000000200")
_FIXED_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000201")


@pytest.mark.phase1
def test_product_state_defaults_match_spec():
    # Arrange / Act
    state = ProductState(
        user_id=_FIXED_USER_ID,
        project_id=_FIXED_PROJECT_ID,
        raw_input="smart desk lamp",
    )

    # Assert
    assert state.current_phase == "clarify"
    assert state.clarification_history == []
    assert state.reference_findings is None
    assert state.product_spec is None
    assert state.gate_plan_approved is False
    assert state.gate_review_approved is False
    assert state.gate_fab_confirmed is False
    assert state.user_intent_to_plan is False
    assert state.review_reports == []
    assert state.fab_orders == []


@pytest.mark.phase1
def test_enclosure_pcb_contract_round_trips_via_json():
    # Arrange
    contract = EnclosurePCBContract(
        pcb_outline_mm=[(0.0, 0.0), (50.0, 0.0), (50.0, 30.0), (0.0, 30.0)],
        mounting_holes=[
            Hole(x_mm=5.0, y_mm=5.0, diameter_mm=3.2, purpose="mounting"),
            Hole(x_mm=45.0, y_mm=25.0, diameter_mm=3.2, purpose="mounting"),
        ],
        last_modified_by="pcb",
    )

    # Act
    dumped = contract.model_dump(mode="json")
    restored = EnclosurePCBContract.model_validate(dumped)

    # Assert
    assert restored.last_modified_by == "pcb"
    assert len(restored.mounting_holes) == 2  # noqa: PLR2004 — round-trip count
    assert restored.mounting_holes[0].diameter_mm == pytest.approx(3.2)
    assert restored.pcb_thickness_max_mm == pytest.approx(1.6)  # default
    assert restored.revision == 0


@pytest.mark.phase1
def test_product_spec_with_frozen_true_round_trips():
    # Arrange
    spec = ProductSpec(
        title="Smart Desk Lamp",
        summary="USB-C powered desk lamp.",
        requirements=[
            Requirement(
                id="R01",
                statement="Lamp must run on USB-C PD.",
                category="functional",
                priority="must",
            )
        ],
        constraints=Constraints(
            target_unit_count=500,
            compliance_markets=["CN", "EU"],
        ),
        target_use_case="office desk task lighting",
        frozen=True,
    )

    # Act
    dumped = spec.model_dump(mode="json")
    restored = ProductSpec.model_validate(dumped)

    # Assert
    assert restored.frozen is True
    assert restored.title == "Smart Desk Lamp"
    assert len(restored.requirements) == 1
    assert restored.constraints.compliance_markets == ["CN", "EU"]


@pytest.mark.phase1
def test_product_state_requires_user_and_project_ids():
    """The three primary fields are required — construction must fail without them."""
    # Act / Assert
    with pytest.raises(ValidationError):
        ProductState()  # type: ignore[call-arg]
