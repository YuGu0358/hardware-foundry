"""Phase 1 unit tests for the LangGraph workflow topology.

These tests inspect graph structure only — no LLM, no DB, no checkpointer.
"""

from __future__ import annotations

import pytest
from foundry_api.workflow import _build_graph


@pytest.mark.phase1
def test_build_graph_has_expected_nodes():
    # Arrange / Act
    graph = _build_graph()

    # Assert — Compliance landed in PR #9 so we expect 4 nodes
    assert set(graph.nodes.keys()) == {
        "reference_search",
        "clarifier",
        "planner",
        "compliance",
    }


@pytest.mark.phase1
def test_build_graph_compiles_without_checkpointer():
    # Arrange
    graph = _build_graph()

    # Act / Assert — compile must succeed even with no checkpointer
    compiled = graph.compile()
    assert compiled is not None
