"""Phase 3 slice 2 unit tests for ComponentSelectionAgent + StubSupplierAdapter.

Slice 2 swaps the heuristic ``_query_from_requirement`` for an LLM call, so
agent-level tests now monkeypatch ``BaseAgent.llm`` via a ``mock_llm`` fixture
(same pattern as the Phase 1 planner tests).
"""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from foundry_agent_base import (
    BOM,
    AgentContext,
    BaseAgent,
    ComponentMatch,
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


def _three_query_payload() -> str:
    return json.dumps(
        {
            "queries": [
                {
                    "role": "main-mcu",
                    "parameters": {"vin_max_mv": 5500, "interface": "BLE, USB"},
                    "quantity": 1,
                    "preferred_supplier": "any",
                },
                {
                    "role": "led-driver",
                    "parameters": {"output_current_ma": 700},
                    "quantity": 1,
                    "preferred_supplier": "any",
                },
                {
                    "role": "usb-c-connector",
                    "parameters": {"package": "SMT"},
                    "quantity": 1,
                    "preferred_supplier": "any",
                },
            ],
            "summary": "Three-piece skeleton BOM for a USB-C BLE desk lamp.",
        }
    )


@pytest.fixture
def mock_llm(monkeypatch):
    state: dict[str, str] = {"payload": ""}

    async def fake_llm(self, messages, **kw):
        return state["payload"]

    monkeypatch.setattr(BaseAgent, "llm", fake_llm)
    return state


@pytest.fixture
def boom_llm(monkeypatch):
    """LLM monkeypatch that raises if called — used to assert early-return paths."""

    async def exploding_llm(self, messages, **kw):
        raise AssertionError("BaseAgent.llm must not be called when product_spec is None")

    monkeypatch.setattr(BaseAgent, "llm", exploding_llm)


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
async def test_component_selection_agent_with_spec_emits_bom(mock_llm):
    # Arrange
    mock_llm["payload"] = _three_query_payload()
    spec = _make_spec_with_mix()
    agent = ComponentSelectionAgent(adapter=StubSupplierAdapter())

    # Act
    update = await agent.run(_make_state(spec), _make_ctx())

    # Assert
    assert isinstance(update, dict)
    assert update["current_phase"] == "design"
    bom = update["bom"]
    assert isinstance(bom, BOM)
    assert len(bom.items) == _EXPECTED_MATCH_COUNT  # one BOM row per LLM query
    for item in bom.items:
        # Stub-sourced rows are coerced to "other" in the BOM but remain
        # identifiable via the "STUB-" mpn prefix from StubSupplierAdapter.
        assert item.supplier == "other"
        assert item.mpn.startswith("STUB-")
        # Stub returns 3 candidates; the chosen mpn is excluded from alternatives,
        # leaving 2 alternates per item.
        assert len(item.alternatives) == _EXPECTED_MATCH_COUNT - 1
    expected_total = sum(it.unit_price_cents * it.quantity for it in bom.items)
    assert bom.total_cost_cents == expected_total


@pytest.mark.phase3
async def test_component_selection_agent_no_spec_returns_empty_bom(boom_llm):
    # Arrange — `boom_llm` ensures the LLM is NEVER called on this path.
    agent = ComponentSelectionAgent(adapter=StubSupplierAdapter())

    # Act
    update = await agent.run(_make_state(spec=None), _make_ctx())

    # Assert
    assert update == {"bom": None}


@pytest.mark.phase3
async def test_component_selection_extractor_bad_json_raises_runtime_error(mock_llm):
    # Arrange
    mock_llm["payload"] = "not-json-at-all {{"
    agent = ComponentSelectionAgent(adapter=StubSupplierAdapter())

    # Act / Assert
    with pytest.raises(
        RuntimeError,
        match=r"^component_selection: failed to parse extractor JSON",
    ):
        await agent.run(_make_state(_make_spec_with_mix()), _make_ctx())


@pytest.mark.phase3
async def test_component_selection_extractor_invalid_schema_raises_runtime_error(mock_llm):
    # Arrange — valid JSON but the required `queries` field is missing.
    mock_llm["payload"] = json.dumps({"summary": "no queries field here"})
    agent = ComponentSelectionAgent(adapter=StubSupplierAdapter())

    # Act / Assert
    with pytest.raises(
        RuntimeError,
        match=r"^component_selection: failed to parse extractor JSON",
    ):
        await agent.run(_make_state(_make_spec_with_mix()), _make_ctx())


_EMPTY_CALL_INDEX = 2  # 1-indexed: second call returns no matches


class _SelectiveAdapter:
    """Test adapter that returns empty matches for the second query, three for the others."""

    name = "selective-test"

    def __init__(self) -> None:
        self._calls = 0

    async def search(self, query: ComponentQuery) -> list[ComponentMatch]:
        self._calls += 1
        if self._calls == _EMPTY_CALL_INDEX:
            return []
        return [
            ComponentMatch(
                mpn=f"FAKE-{query.role}-{i + 1}",
                manufacturer=f"FakeMfg{i + 1}",
                description=f"Fake candidate {i + 1} for {query.role}",
                supplier="digikey",
                supplier_part_number=f"FAKE-SPN-{query.role}-{i + 1}",
                unit_price_cents=100 + i * 50,
                in_stock=True,
                moq=1,
                datasheet_url=None,
                parametric=dict(query.parameters),
                score=0.9 - i * 0.2,
            )
            for i in range(_EXPECTED_MATCH_COUNT)
        ]


@pytest.mark.phase3
async def test_component_selection_extractor_skips_query_with_no_matches(mock_llm):
    # Arrange — 3 queries; the adapter returns [] for query[1] only.
    mock_llm["payload"] = _three_query_payload()
    adapter = _SelectiveAdapter()
    agent = ComponentSelectionAgent(adapter=adapter)

    # Act
    update = await agent.run(_make_state(_make_spec_with_mix()), _make_ctx())

    # Assert
    bom = update["bom"]
    assert isinstance(bom, BOM)
    # Two BOM rows: query[0] and query[2] only — the empty-match query is skipped.
    assert len(bom.items) == _EXPECTED_MATCH_COUNT - 1
    assert adapter._calls == _EXPECTED_MATCH_COUNT  # adapter still queried for all 3
    # Verify we picked the expected mpns (query[1] => led-driver omitted).
    selected_mpns = {item.mpn for item in bom.items}
    assert "FAKE-main-mcu-1" in selected_mpns
    assert "FAKE-usb-c-connector-1" in selected_mpns
    assert not any("led-driver" in mpn for mpn in selected_mpns)
