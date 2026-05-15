"""FastAPI entrypoint — exposes the LangGraph agent pipeline over HTTP.

Run locally:
    uv run uvicorn foundry_api.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from foundry_api import __version__
from foundry_api.config import settings
from foundry_api.projects.router import router as projects_router
from foundry_api.workflow import lifespan_graph

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
    description="Phase 1 — multi-turn Clarifier with LangGraph interrupt + Project entity.",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------


app.include_router(projects_router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Top-level endpoints
# ---------------------------------------------------------------------------


@app.get("/api/v1/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "foundry_api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
