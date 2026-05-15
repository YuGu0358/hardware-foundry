"""FastAPI router for the Project entity.

Endpoints:
- POST   /api/v1/projects                    create + run Clarifier (interrupts after 1st round)
- GET    /api/v1/projects                    list current user's projects
- GET    /api/v1/projects/{id}               full project state + history
- POST   /api/v1/projects/{id}/messages      user replies, graph resumes
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from foundry_agent_base import Message, MessageRole
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from foundry_api.config import settings
from foundry_api.db import get_session
from foundry_api.projects.models import Project
from foundry_api.projects.repository import ProjectRepository
from foundry_api.workflow import (
    apply_command_approve_plan,
    apply_command_start_planning,
    read_state,
    resume_with_message,
    start_project_run,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    raw_input: str = Field(min_length=1, max_length=4000)
    title: str | None = Field(default=None, max_length=200)


class ProjectSummary(BaseModel):
    id: UUID
    title: str | None
    current_phase: str
    raw_input: str
    created_at: str  # ISO-8601
    updated_at: str

    @classmethod
    def from_orm(cls, p: Project) -> ProjectSummary:
        return cls(
            id=p.id,
            title=p.title,
            current_phase=p.current_phase,
            raw_input=p.raw_input,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
        )


class ProjectDetail(BaseModel):
    project: ProjectSummary
    state: dict  # serialised ProductState


class PostMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_repo(session: Annotated[AsyncSession, Depends(get_session)]) -> ProjectRepository:
    return ProjectRepository(session=session)


def get_graph(request: Request) -> object:
    """Pull the compiled LangGraph app off the FastAPI lifespan state."""
    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        raise HTTPException(status_code=503, detail="graph not initialised")
    return graph


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
async def create_project(
    req: CreateProjectRequest,
    repo: Annotated[ProjectRepository, Depends(get_repo)],
    request: Request,
) -> ProjectDetail:
    """Create a project and run Clarifier once. Graph interrupts after Clarifier."""
    project = await repo.create(
        user_id=settings.default_user_id,
        raw_input=req.raw_input,
        title=req.title,
    )

    final_state = await start_project_run(
        compiled_app=get_graph(request),
        project_id=project.id,
        user_id=settings.default_user_id,
        raw_input=req.raw_input,
    )

    return ProjectDetail(
        project=ProjectSummary.from_orm(project),
        state=final_state.model_dump(mode="json"),
    )


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    repo: Annotated[ProjectRepository, Depends(get_repo)],
    limit: int = 50,
    offset: int = 0,
) -> list[ProjectSummary]:
    rows = await repo.list_for_user(settings.default_user_id, limit=limit, offset=offset)
    return [ProjectSummary.from_orm(r) for r in rows]


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: UUID,
    repo: Annotated[ProjectRepository, Depends(get_repo)],
    request: Request,
) -> ProjectDetail:
    project = await repo.get_for_user(project_id, settings.default_user_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    state = await read_state(get_graph(request), project_id)
    return ProjectDetail(
        project=ProjectSummary.from_orm(project),
        state=state.model_dump(mode="json") if state else {},
    )


@router.post("/{project_id}/messages", response_model=ProjectDetail)
async def post_message(
    project_id: UUID,
    body: PostMessageRequest,
    repo: Annotated[ProjectRepository, Depends(get_repo)],
    request: Request,
) -> ProjectDetail:
    """Append a user message and resume the graph for one more turn."""
    project = await repo.get_for_user(project_id, settings.default_user_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    user_msg = Message(role=MessageRole.USER, content=body.content)

    final_state = await resume_with_message(
        compiled_app=get_graph(request),
        project_id=project_id,
        user_message=user_msg,
    )

    return ProjectDetail(
        project=ProjectSummary.from_orm(project),
        state=final_state.model_dump(mode="json"),
    )


@router.post("/{project_id}/commands/start-planning", response_model=ProjectDetail)
async def cmd_start_planning(
    project_id: UUID,
    repo: Annotated[ProjectRepository, Depends(get_repo)],
    request: Request,
) -> ProjectDetail:
    """User signals 'OK, start planning'. Triggers Planner; graph stops at planner interrupt."""
    project = await repo.get_for_user(project_id, settings.default_user_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    final_state = await apply_command_start_planning(
        compiled_app=get_graph(request),
        project_id=project_id,
    )
    await repo.update_phase(project_id, "plan")

    return ProjectDetail(
        project=ProjectSummary.from_orm(project),
        state=final_state.model_dump(mode="json"),
    )


@router.post("/{project_id}/commands/approve-plan", response_model=ProjectDetail)
async def cmd_approve_plan(
    project_id: UUID,
    repo: Annotated[ProjectRepository, Depends(get_repo)],
    request: Request,
) -> ProjectDetail:
    """HITL Gate #1: approve the ProductSpec and exit Phase 1."""
    project = await repo.get_for_user(project_id, settings.default_user_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    final_state = await apply_command_approve_plan(
        compiled_app=get_graph(request),
        project_id=project_id,
    )
    await repo.update_phase(project_id, "design")

    return ProjectDetail(
        project=ProjectSummary.from_orm(project),
        state=final_state.model_dump(mode="json"),
    )
