"""Phase 1 unit tests for ReferenceSearchAgent.

Tavily HTTP and BaseAgent.llm are both mocked. The TAVILY_API_KEY env var is
controlled per-test so we can exercise the no-key short-circuit path.
"""

from __future__ import annotations

import json
from uuid import UUID

import pytest
import tavily
from foundry_agent_base import AgentContext, BaseAgent, ProductState, ReferenceProduct
from foundry_agent_reference_search import ReferenceSearchAgent

_FIXED_USER_ID = UUID("00000000-0000-0000-0000-000000000100")
_FIXED_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000101")


def _make_state() -> ProductState:
    return ProductState(
        user_id=_FIXED_USER_ID,
        project_id=_FIXED_PROJECT_ID,
        raw_input="smart desk lamp",
    )


def _make_ctx() -> AgentContext:
    return AgentContext(
        run_id="run-refsearch",
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


@pytest.mark.phase1
async def test_reference_search_no_api_key_returns_empty(monkeypatch):
    # Arrange
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    async def boom_llm(self, messages, **kw):
        raise AssertionError("llm should not be called when no API key")

    monkeypatch.setattr(BaseAgent, "llm", boom_llm)

    def boom_search(self, **kw):
        raise AssertionError("Tavily search should not be called when no API key")

    monkeypatch.setattr(tavily.TavilyClient, "search", boom_search)

    # Act
    update = await ReferenceSearchAgent().run(_make_state(), _make_ctx())

    # Assert
    assert update == {"reference_findings": []}


@pytest.mark.phase1
async def test_reference_search_tavily_failure_returns_empty(monkeypatch):
    # Arrange
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    def fail_search(self, **kw):
        raise RuntimeError("tavily backend exploded")

    monkeypatch.setattr(tavily.TavilyClient, "search", fail_search)

    # Act
    update = await ReferenceSearchAgent().run(_make_state(), _make_ctx())

    # Assert
    assert update == {"reference_findings": []}


@pytest.mark.phase1
async def test_reference_search_happy_path_returns_products(monkeypatch, mock_llm):
    # Arrange
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    fake_results = {
        "results": [
            {
                "title": f"Product {i}",
                "url": f"https://example.com/p{i}",
                "content": f"Description of product {i}, used in similar context.",
            }
            for i in range(1, 5)
        ]
    }

    def fake_search(self, **kw):
        return fake_results

    monkeypatch.setattr(tavily.TavilyClient, "search", fake_search)

    products_payload = [
        {
            "name": f"Reference Lamp {i}",
            "url": f"https://example.com/p{i}",
            "summary": f"Summary of reference lamp {i}.",
            "design_takeaways": [f"takeaway-{i}-a", f"takeaway-{i}-b"],
            "similarity_score": 0.5 + 0.05 * i,
        }
        for i in range(1, 5)
    ]
    mock_llm["payload"] = json.dumps({"products": products_payload})

    # Act
    update = await ReferenceSearchAgent().run(_make_state(), _make_ctx())

    # Assert
    findings = update["reference_findings"]
    assert 3 <= len(findings) <= 5  # noqa: PLR2004 - agent clamps to 3-5
    assert all(isinstance(p, ReferenceProduct) for p in findings)
    assert findings[0].name == "Reference Lamp 1"


@pytest.mark.phase1
async def test_reference_search_bad_llm_json_returns_empty(monkeypatch, mock_llm):
    """If the summarization LLM returns garbage, the agent must no-op gracefully."""
    # Arrange
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    def fake_search(self, **kw):
        return {
            "results": [
                {"title": "x", "url": "https://example.com/x", "content": "..."},
            ]
        }

    monkeypatch.setattr(tavily.TavilyClient, "search", fake_search)
    mock_llm["payload"] = "not valid json"

    # Act
    update = await ReferenceSearchAgent().run(_make_state(), _make_ctx())

    # Assert
    assert update == {"reference_findings": []}
