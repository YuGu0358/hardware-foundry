"""LangGraph workflow assembly + multi-turn helpers.

Phase 1 graph is a single Clarifier node with interrupt_after, so the graph
pauses for user input after each clarifier turn. The user resumes by POSTing
a message; the graph then runs another clarifier turn (or, once user_intent_to_plan
becomes True in a later PR, routes to Planner).

thread_id == project_id, so all turns of one project share state in the
LangGraph checkpointer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from foundry_agent_base import AgentContext, Message, ProductState
from foundry_agent_clarifier import ClarifierAgent
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from foundry_api.config import langgraph_dsn

# ---------------------------------------------------------------------------
# Node wrappers — adapt BaseAgent.__call__ to LangGraph's (state) -> partial signature
# ---------------------------------------------------------------------------


async def _clarifier_node(state: ProductState) -> dict:
    agent = ClarifierAgent()
    ctx = AgentContext(
        run_id=str(state.run_id),
        user_id=str(state.user_id),
        project_id=str(state.project_id),
    )
    return await agent(state, ctx)


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def _build_graph() -> StateGraph:
    graph = StateGraph(ProductState)
    graph.add_node("clarifier", _clarifier_node)
    graph.add_edge(START, "clarifier")
    graph.add_edge("clarifier", END)
    return graph


@asynccontextmanager
async def lifespan_graph() -> AsyncIterator[object]:
    """Yield a compiled LangGraph app with a live Postgres checkpointer.

    `interrupt_after=["clarifier"]` makes the graph pause AFTER each clarifier
    turn. The router resumes the graph by calling `resume_with_message()`.
    """
    async with AsyncPostgresSaver.from_conn_string(langgraph_dsn()) as checkpointer:
        await checkpointer.setup()
        compiled = _build_graph().compile(
            checkpointer=checkpointer,
            interrupt_after=["clarifier"],
        )
        yield compiled


# ---------------------------------------------------------------------------
# Multi-turn helpers
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
    # ainvoke returns the state AFTER the interrupt fires (so: post-clarifier state)
    await compiled_app.ainvoke(initial, config=config)  # type: ignore[attr-defined]
    return await _load_state(compiled_app, project_id)


async def resume_with_message(
    compiled_app: object,
    *,
    project_id: UUID,
    user_message: Message,
) -> ProductState:
    """Append `user_message` to clarification_history and resume the graph for one turn."""
    config = _config_for(project_id)
    current = await _load_state(compiled_app, project_id)
    if current is None:
        raise ValueError(f"no checkpoint found for project {project_id}")

    new_history = [*current.clarification_history, user_message]
    # update_state merges the partial dict using LangGraph's per-field reducers
    await compiled_app.aupdate_state(  # type: ignore[attr-defined]
        config,
        values={"clarification_history": new_history},
    )
    # Resume from interrupt — passing None means "continue from where we paused"
    await compiled_app.ainvoke(None, config=config)  # type: ignore[attr-defined]
    return await _load_state(compiled_app, project_id)


async def read_state(compiled_app: object, project_id: UUID) -> ProductState | None:
    """Read the latest checkpointed state for a project (no graph execution)."""
    return await _load_state(compiled_app, project_id)


async def _load_state(compiled_app: object, project_id: UUID) -> ProductState | None:
    snapshot = await compiled_app.aget_state(_config_for(project_id))  # type: ignore[attr-defined]
    if not snapshot or not snapshot.values:
        return None
    return ProductState.model_validate(snapshot.values)
