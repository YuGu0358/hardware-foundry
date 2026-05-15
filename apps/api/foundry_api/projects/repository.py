"""Async CRUD operations for the `Project` entity."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from foundry_api.projects.models import Project


@dataclass(frozen=True)
class ProjectRepository:
    """Thin async CRUD wrapper around AsyncSession scoped to one request."""

    session: AsyncSession

    async def create(
        self,
        *,
        user_id: UUID,
        raw_input: str,
        title: str | None = None,
    ) -> Project:
        project = Project(user_id=user_id, raw_input=raw_input, title=title)
        self.session.add(project)
        await self.session.flush()
        return project

    async def get(self, project_id: UUID) -> Project | None:
        return await self.session.get(Project, project_id)

    async def get_for_user(self, project_id: UUID, user_id: UUID) -> Project | None:
        """Get a project iff it belongs to user_id. MVP single-tenant safety net."""
        stmt = select(Project).where(Project.id == project_id, Project.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Project]:
        stmt = (
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def update_phase(self, project_id: UUID, new_phase: str) -> None:
        project = await self.session.get(Project, project_id)
        if project is None:
            raise ValueError(f"project {project_id} not found")
        project.current_phase = new_phase
