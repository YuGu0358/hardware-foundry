"""Phase 1 unit tests for ClarifierAgent.

LLM access is mocked via monkeypatching `BaseAgent.llm` — no network, no real
model calls. Each test builds a minimal `ProductState` with fixed UUIDs so the
tests are deterministic.
"""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from foundry_agent_base import AgentContext, BaseAgent, Message, MessageRole, ProductState
from foundry_agent_clarifier import ClarifierAgent

_FIXED_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_FIXED_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
def mock_llm(monkeypatch):
    """Replace BaseAgent.llm with a stub returning a configurable payload."""
    state: dict[str, str] = {"payload": ""}

    async def fake_llm(self, messages, **kw):
        return state["payload"]

    monkeypatch.setattr(BaseAgent, "llm", fake_llm)
    return state


def _make_state() -> ProductState:
    return ProductState(
        user_id=_FIXED_USER_ID,
        project_id=_FIXED_PROJECT_ID,
        raw_input="smart desk lamp",
    )


def _make_ctx() -> AgentContext:
    return AgentContext(
        run_id="run-1",
        user_id=str(_FIXED_USER_ID),
        project_id=str(_FIXED_PROJECT_ID),
    )


@pytest.mark.phase1
async def test_clarifier_happy_path_appends_assistant_message(mock_llm):
    # Arrange
    mock_llm["payload"] = json.dumps(
        {
            "summary": "Clarifying smart desk lamp requirements",
            "questions": [
                {
                    "id": "Q1",
                    "topic": "power",
                    "question": "Should the lamp run on USB-C or a wall adapter?",
                    "sample_options": ["USB-C", "Wall adapter"],
                    "rationale": "Power source drives enclosure size.",
                },
                {
                    "id": "Q2",
                    "topic": "control",
                    "question": "Touch dimmer, BLE app, or both?",
                    "sample_options": ["Touch", "BLE", "Both"],
                },
            ],
        }
    )
    agent = ClarifierAgent()
    state = _make_state()

    # Act
    update = await agent.run(state, _make_ctx())

    # Assert
    assert isinstance(update, dict)
    assert update["current_phase"] == "clarify"
    history = update["clarification_history"]
    assert len(history) == 1
    msg = history[0]
    assert msg.role == MessageRole.ASSISTANT
    assert "USB-C or a wall adapter" in msg.content


@pytest.mark.phase1
async def test_clarifier_bad_json_raises_runtime_error(mock_llm):
    # Arrange
    mock_llm["payload"] = "not-json-at-all {{{"
    agent = ClarifierAgent()

    # Act / Assert
    with pytest.raises(RuntimeError, match="clarifier: failed to parse"):
        await agent.run(_make_state(), _make_ctx())


@pytest.mark.phase1
async def test_clarifier_preserves_existing_history(mock_llm):
    """The agent must append to, not replace, existing clarification_history."""
    # Arrange
    mock_llm["payload"] = json.dumps(
        {"summary": "", "questions": [{"id": "Q1", "topic": "x", "question": "Q?"}]}
    )
    prior = Message(role=MessageRole.USER, content="initial idea")
    state = _make_state().model_copy(update={"clarification_history": [prior]})

    # Act
    update = await ClarifierAgent().run(state, _make_ctx())

    # Assert
    history = update["clarification_history"]
    assert len(history) == 2  # noqa: PLR2004 — prior USER + new ASSISTANT
    assert history[0].content == "initial idea"
    assert history[1].role == MessageRole.ASSISTANT
