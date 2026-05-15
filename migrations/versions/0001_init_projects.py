"""init projects table

Revision ID: 0001_init_projects
Revises:
Create Date: 2026-05-15

Creates the `projects` table — the business-level container for a hardware
design run. LangGraph's own checkpoint tables are created at runtime by
`AsyncPostgresSaver.setup()` and are NOT managed by Alembic.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "0001_init_projects"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("raw_input", sa.Text(), nullable=False),
        sa.Column(
            "current_phase",
            sa.String(length=20),
            nullable=False,
            server_default="clarify",
        ),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_projects_user_id_created_at",
        "projects",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_projects_user_id_created_at", table_name="projects")
    op.drop_table("projects")
