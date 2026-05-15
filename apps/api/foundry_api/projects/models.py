"""SQLAlchemy ORM model for the `projects` table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from foundry_api.db import Base


class Project(Base):
    """A user's hardware design project.

    One Project ↔ one LangGraph thread (thread_id == project_id). The
    LangGraph checkpoint tables hold per-turn ProductState; this row holds
    business metadata that survives independently of the checkpointer.
    """

    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    current_phase: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="clarify",
        server_default="clarify",
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_projects_user_id_created_at", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} user={self.user_id} phase={self.current_phase}>"
