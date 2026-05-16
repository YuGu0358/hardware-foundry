"""Async SQLAlchemy engine + session factory.

Used by repositories and Alembic migrations. The engine is created at module
import time; FastAPI dependencies acquire short-lived `AsyncSession`s via
`get_session()`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from foundry_api.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# Supabase's transaction pooler (pgbouncer) does not support prepared statements;
# disable asyncpg's prepared-statement caches so the same engine works against
# both local Postgres and the pooled cloud DSN.
_ASYNCPG_CONNECT_ARGS: dict[str, Any] = {
    "statement_cache_size": 0,
    "prepared_statement_cache_size": 0,
}

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args=_ASYNCPG_CONNECT_ARGS if "+asyncpg" in settings.database_url else {},
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields a session, commits on success, rolls back on error."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def alembic_sync_url() -> str:
    """Alembic uses sync psycopg, not asyncpg — translate the DSN once here."""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)


# Re-exported so migrations/env.py can `from foundry_api.db import metadata`
metadata: Any = Base.metadata
