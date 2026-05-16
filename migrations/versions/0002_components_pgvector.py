"""components table + pgvector embeddings

Revision ID: 0002_components_pgvector
Revises: 0001_init_projects
Create Date: 2026-05-16

Creates the `components` table — Phase 3 catalog of supplier parts with
1536-dim embeddings for semantic similarity search, and a column linking to
the Supabase Storage object holding the upstream datasheet / 3D model.

The pgvector extension is installed into the `extensions` schema (Supabase
convention). The HNSW index over `embedding` uses cosine distance, which
matches OpenAI / text-embedding-3-small style normalized vectors.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

revision: str = "0002_components_pgvector"
down_revision: str | Sequence[str] | None = "0001_init_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector lives under the `extensions` schema on Supabase. Idempotent so
    # local docker DBs that haven't been bootstrapped pick it up too.
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions"))

    op.create_table(
        "components",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("mpn", sa.Text(), nullable=False),
        sa.Column("manufacturer", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("supplier", sa.Text(), nullable=False),
        sa.Column("supplier_part_number", sa.Text(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=True),
        sa.Column(
            "in_stock",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column("moq", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("datasheet_url", sa.Text(), nullable=True),
        sa.Column(
            "parametric",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("datasheet_object_key", sa.Text(), nullable=True),
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

    # Add the pgvector column out-of-band so we don't depend on a SQLAlchemy
    # pgvector dialect plugin at migration time.
    op.execute(sa.text("ALTER TABLE components ADD COLUMN embedding vector(1536)"))

    op.create_index(
        "ux_components_supplier_part_number",
        "components",
        ["supplier", "supplier_part_number"],
        unique=True,
    )
    op.create_index("ix_components_mpn", "components", ["mpn"])

    # HNSW index for fast cosine-similarity ANN over `embedding`. Safe to
    # drop and recreate without data loss — it's a pure index over the column.
    op.execute(
        sa.text(
            "CREATE INDEX ix_components_embedding_hnsw "
            "ON components USING hnsw (embedding vector_cosine_ops)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_components_embedding_hnsw"))
    op.drop_index("ix_components_mpn", table_name="components")
    op.drop_index("ux_components_supplier_part_number", table_name="components")
    op.drop_table("components")
    # Deliberately do NOT drop the `vector` extension — other tables (now or
    # later) may rely on it.
