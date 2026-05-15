"""FastAPI entrypoint — exposes the LangGraph agent pipeline over HTTP.

Run locally:
    uv run uvicorn foundry_api.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from foundry_agent_base import ProductState
from foundry_api import __version__
from foundry_api.config import settings
from foundry_api.workflow import invoke_initial_run, lifespan_graph

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Lifespan — compile LangGraph once at startup, share across requests
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("api.startup", version=__version__)
    async with lifespan_graph() as compiled_graph:
        app.state.graph = compiled_graph
        yield
    logger.info("api.shutdown")


app = FastAPI(
    title="Hardware Foundry API",
    version=__version__,
    description="Phase 0 — connectivity scaffold. POST /api/v1/runs to drive the EchoAgent.",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class CreateRunRequest(BaseModel):
    raw_input: str = Field(min_length=1, max_length=4000)


class CreateRunResponse(BaseModel):
    run_id: str
    project_id: str
    final_state: dict


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/v1/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/api/v1/runs", response_model=CreateRunResponse, status_code=201)
async def create_run(req: CreateRunRequest) -> CreateRunResponse:
    """Phase 0: synchronously drive the EchoAgent and return final state.

    Later phases return run_id immediately and stream progress via SSE.
    """
    try:
        final: ProductState = await invoke_initial_run(app.state.graph, req.raw_input)
    except Exception as exc:
        logger.exception("api.run_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"run failed: {exc}") from exc

    return CreateRunResponse(
        run_id=str(final.run_id),
        project_id=str(final.project_id),
        final_state=final.model_dump(mode="json"),
    )


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "foundry_api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
