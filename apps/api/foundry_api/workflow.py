"""LangGraph workflow assembly + multi-turn / command helpers.

Phase 1 + Phase 2 topology:

    START
      ├─(conditional, _route_after_start)─►
      │     reference_findings is None → reference_search → clarifier
      │     else                       → clarifier
      ▼
    clarifier (interrupt_after)
      │
      ├─(conditional, _route_after_clarifier)─►
      │     user_intent_to_plan → planner
      │     else                → clarifier (next round, after next user msg)
      ▼
    planner (interrupt_after)
      │
      ├─(conditional, _route_after_planner)─►
      │     gate_plan_approved → compliance
      │     else               → clarifier (revision loop)
      ▼
    compliance (interrupt_after)
      │
      └─► feasibility (interrupt_after)
              │
              └─► END

Phase 2 MVP chains Compliance → Feasibility automatically once the plan is
approved. No `gate_compliance_approved` flag yet — the human review gate
between the two lands in Phase 3.

thread_id == project_id, so all turns of one project share state in the
LangGraph checkpointer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from foundry_agent_base import AgentContext, Message, ProductState
from foundry_agent_clarifier import ClarifierAgent
from foundry_agent_compliance import ComplianceAgent
from foundry_agent_feasibility import FeasibilityAgent
from foundry_agent_planner import PlannerAgent
from foundry_agent_reference_search import ReferenceSearchAgent
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from foundry_api.config import langgraph_dsn

# ---------------------------------------------------------------------------
# Node wrappers
# ---------------------------------------------------------------------------


def _make_ctx(state: ProductState) -> AgentContext:
    return AgentContext(
        run_id=str(state.run_id),
        user_id=str(state.user_id),
        project_id=str(state.project_id),
    )


async def _reference_search_node(state: ProductState) -> dict:
    """Runs once at project start; later turns skip via _route_after_start."""
    return await ReferenceSearchAgent()(state, _make_ctx(state))


async def _clarifier_node(state: ProductState) -> dict:
    return await ClarifierAgent()(state, _make_ctx(state))


async def _planner_node(state: ProductState) -> dict:
    return await PlannerAgent()(state, _make_ctx(state))


async def _compliance_node(state: ProductState) -> dict:
    return await ComplianceAgent()(state, _make_ctx(state))


async def _feasibility_node(state: ProductState) -> dict:
    return await FeasibilityAgent()(state, _make_ctx(state))


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------


def _route_after_start(state: ProductState) -> str:
    return "clarifier" if state.reference_findings is not None else "reference_search"


def _route_after_clarifier(state: ProductState) -> str:
    return "planner" if state.user_intent_to_plan else "clarifier"


def _route_after_planner(state: ProductState) -> str:
    return "compliance" if state.gate_plan_approved else "clarifier"


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def _build_graph() -> StateGraph:
    graph = StateGraph(ProductState)

    graph.add_node("reference_search", _reference_search_node)
    graph.add_node("clarifier", _clarifier_node)
    graph.add_node("planner", _planner_node)
    graph.add_node("compliance", _compliance_node)
    graph.add_node("feasibility", _feasibility_node)

    graph.add_conditional_edges(
        START,
        _route_after_start,
        {"reference_search": "reference_search", "clarifier": "clarifier"},
    )
    graph.add_edge("reference_search", "clarifier")
    graph.add_conditional_edges(
        "clarifier",
        _route_after_clarifier,
        {"clarifier": "clarifier", "planner": "planner"},
    )
    graph.add_conditional_edges(
        "planner",
        _route_after_planner,
        {"compliance": "compliance", "clarifier": "clarifier"},
    )
    graph.add_edge("compliance", "feasibility")
    graph.add_edge("feasibility", END)
    return graph


@asynccontextmanager
async def lifespan_graph() -> AsyncIterator[object]:
    """Yield a compiled LangGraph app with a live Postgres checkpointer.

    `interrupt_after=["clarifier", "planner", "compliance", "feasibility"]`
    pauses the graph after each of these nodes; the router resumes via
    /messages or /commands/* endpoints. Phase 2 MVP has no `compliance`
    or `feasibility` gate flags — the graph chains compliance → feasibility
    → END once the plan-approval gate has been satisfied. Human review of
    the feasibility report itself lands in Phase 3.
    """
    async with AsyncPostgresSaver.from_conn_string(langgraph_dsn()) as checkpointer:
        await checkpointer.setup()
        compiled = _build_graph().compile(
            checkpointer=checkpointer,
            interrupt_after=["clarifier", "planner", "compliance", "feasibility"],
        )
        yield compiled


# ---------------------------------------------------------------------------
# Multi-turn / command helpers
# ---------------------------------------------------------------------------


def _config_for(project_id: UUID) -> dict:
    return {"configurable": {"thread_id": str(project_id)}}


async def start_project_run(
    compiled_app: object,
    *,
    project_id: UUID,
    user_id: UUID,
    raw_input: str,
) -> ProductState:
    """Kick off the graph for a fresh project. Returns state after first clarifier turn."""
    initial = ProductState(
        user_id=user_id,
        project_id=project_id,
        raw_input=raw_input,
    )
    config = _config_for(project_id)
    await compiled_app.ainvoke(initial, config=config)  # type: ignore[attr-defined]
    state = await _load_state(compiled_app, project_id)
    assert state is not None  # checkpointer just wrote it
    return state


async def resume_with_message(
    compiled_app: object,
    *,
    project_id: UUID,
    user_message: Message,
) -> ProductState:
    """Append `user_message` to history, then resume one graph turn."""
    current = await _require_state(compiled_app, project_id)
    new_history = [*current.clarification_history, user_message]
    await _patch_state(compiled_app, project_id, {"clarification_history": new_history})
    await compiled_app.ainvoke(None, config=_config_for(project_id))  # type: ignore[attr-defined]
    state = await _load_state(compiled_app, project_id)
    assert state is not None
    return state


async def apply_command_start_planning(
    compiled_app: object,
    *,
    project_id: UUID,
) -> ProductState:
    """User signals 'OK, plan it'. Sets user_intent_to_plan=True and resumes;
    graph then routes clarifier→planner and stops at planner interrupt with
    a fresh ProductSpec attached to state."""
    await _require_state(compiled_app, project_id)
    await _patch_state(compiled_app, project_id, {"user_intent_to_plan": True})
    await compiled_app.ainvoke(None, config=_config_for(project_id))  # type: ignore[attr-defined]
    state = await _load_state(compiled_app, project_id)
    assert state is not None
    return state


async def apply_command_approve_plan(
    compiled_app: object,
    *,
    project_id: UUID,
) -> ProductState:
    """HITL Gate #1. Sets gate_plan_approved=True and resumes; planner→
    compliance→feasibility, then graph stops at the feasibility interrupt
    with a fresh ComplianceReport and FeasibilityReport attached to state."""
    await _require_state(compiled_app, project_id)
    await _patch_state(compiled_app, project_id, {"gate_plan_approved": True})
    await compiled_app.ainvoke(None, config=_config_for(project_id))  # type: ignore[attr-defined]
    state = await _load_state(compiled_app, project_id)
    assert state is not None
    return state


async def read_state(compiled_app: object, project_id: UUID) -> ProductState | None:
    """Read the latest checkpointed state for a project (no graph execution)."""
    return await _load_state(compiled_app, project_id)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _patch_state(compiled_app: object, project_id: UUID, values: dict[str, Any]) -> None:
    await compiled_app.aupdate_state(_config_for(project_id), values=values)  # type: ignore[attr-defined]


async def _require_state(compiled_app: object, project_id: UUID) -> ProductState:
    state = await _load_state(compiled_app, project_id)
    if state is None:
        raise ValueError(f"no checkpoint found for project {project_id}")
    return state


async def _load_state(compiled_app: object, project_id: UUID) -> ProductState | None:
    snapshot = await compiled_app.aget_state(_config_for(project_id))  # type: ignore[attr-defined]
    if not snapshot or not snapshot.values:
        return None
    return ProductState.model_validate(snapshot.values)
