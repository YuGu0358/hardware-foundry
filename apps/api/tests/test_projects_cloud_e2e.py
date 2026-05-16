"""Live cloud round-trip test for the Projects repository.

Skipped by default; only runs when ``RUN_CLOUD_TESTS=1`` is set so CI does not
hit the Supabase project on every push. When enabled, it exercises every
``ProjectRepository`` method against the pooled DSN configured in ``.env``.
"""

from __future__ import annotations

import os
import time
from uuid import UUID

import pytest
import sqlalchemy as sa

if os.environ.get("RUN_CLOUD_TESTS") != "1":
    pytest.skip(
        "cloud tests disabled (set RUN_CLOUD_TESTS=1 to enable)",
        allow_module_level=True,
    )

# Imports below intentionally happen *after* the skip so collection on a
# laptop without DB credentials does not import the live engine module.
from foundry_api.db import SessionLocal
from foundry_api.projects.models import Project
from foundry_api.projects.repository import ProjectRepository

_TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000999")


@pytest.mark.cloud
@pytest.mark.phase3
async def test_projects_repository_round_trip_against_cloud() -> None:
    # Arrange — unique suffix so reruns never collide on raw_input.
    raw_input = f"cloud-e2e smart desk lamp ({int(time.time() * 1000)})"
    created_id: UUID | None = None

    try:
        async with SessionLocal() as session:
            repo = ProjectRepository(session=session)

            # Act — create
            created = await repo.create(user_id=_TEST_USER_ID, raw_input=raw_input)
            await session.commit()
            created_id = created.id

            # Assert — get by id returns the same row
            fetched = await repo.get(created_id)
            assert fetched is not None
            assert fetched.id == created_id
            assert fetched.user_id == _TEST_USER_ID
            assert fetched.raw_input == raw_input
            assert fetched.current_phase == "clarify"

            # Assert — get_for_user honors tenant scoping
            scoped = await repo.get_for_user(created_id, _TEST_USER_ID)
            assert scoped is not None
            assert scoped.id == created_id

            wrong_user = UUID("00000000-0000-0000-0000-000000000001")
            assert await repo.get_for_user(created_id, wrong_user) is None

            # Assert — list_for_user includes the new row
            listed = await repo.list_for_user(_TEST_USER_ID)
            assert any(p.id == created_id for p in listed)

            # Act — update_phase, re-fetch, assert
            await repo.update_phase(created_id, "plan")
            await session.commit()

            session.expire_all()
            updated = await repo.get(created_id)
            assert updated is not None
            assert updated.current_phase == "plan"
    finally:
        # Cleanup — never leave test rows in the cloud DB, even on failure.
        if created_id is not None:
            async with SessionLocal() as cleanup_session:
                await cleanup_session.execute(
                    sa.delete(Project).where(Project.id == created_id)
                )
                await cleanup_session.commit()

                remaining = await cleanup_session.execute(
                    sa.select(sa.func.count()).select_from(Project).where(Project.id == created_id)
                )
                assert remaining.scalar_one() == 0
