"""LangGraph workflow assembly.

Phase 0 graph is a single-node graph (EchoAgent). Subsequent phases will
extend this graph with Clarifier -> Planner -> Compliance -> ... as each
agent comes online.

AsyncPostgresSaver is the checkpointer so run state survives process
restarts and is inspectable in the LangGraph checkpoint tables.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import UUID, uuid4

from foundry_agent_base import AgentContext, ProductState
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from foundry_api.config import langgraph_dsn, settings
from foundry_api.echo_agent import EchoAgent


# ---------------------------------------------------------------------------
# Node wrappers — adapt BaseAgent.__call__ to LangGraph's (state) -> partial signature
# ---------------------------------------------------------------------------


async def _echo_node(state: ProductState) -> dict:
    agent = EchoAgent()
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
    graph.add_node("echo", _echo_node)
    graph.add_edge(START, "echo")
    graph.add_edge("echo", END)
    return graph


@asynccontextmanager
async def lifespan_graph() -> AsyncIterator[object]:
    """Yield a compiled LangGraph app with a live Postgres checkpointer.

    Use as FastAPI lifespan: `async with lifespan_graph() as app: ...`
    """
    async with AsyncPostgresSaver.from_conn_string(langgraph_dsn()) as checkpointer:
        await checkpointer.setup()  # idempotent: creates checkpoint tables on first call
        compiled = _build_graph().compile(checkpointer=checkpointer)
        yield compiled


# ---------------------------------------------------------------------------
# Invocation helper
# ---------------------------------------------------------------------------


async def invoke_initial_run(
    compiled_app: object,
    raw_input: str,
    *,
    project_id: UUID | None = None,
) -> ProductState:
    """Kick off a brand-new run through the graph and return the final state."""
    initial = ProductState(
        user_id=settings.default_user_id,
        project_id=project_id or uuid4(),
        raw_input=raw_input,
    )
    thread_id = str(initial.run_id)
    config = {"configurable": {"thread_id": thread_id}}
    result_dict = await compiled_app.ainvoke(initial, config=config)  # type: ignore[attr-defined]
    return ProductState.model_validate(result_dict)
