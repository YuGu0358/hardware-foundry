"""Application configuration via pydantic-settings.

Reads from the project-root .env (passed in via container env_file or shell exports).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Database / cache ----
    database_url: str = "postgresql+asyncpg://foundry:foundry_dev_pw@localhost:5432/hardware_foundry"
    redis_url: str = "redis://localhost:6379/0"

    # ---- LiteLLM gateway ----
    litellm_url: str = "http://localhost:4000"
    litellm_master_key: str = "sk-litellm-master-dev"

    # ---- Langfuse observability ----
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "http://localhost:3001"

    # ---- API server ----
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ---- MVP single-user ----
    default_user_id: UUID = Field(
        default=UUID("00000000-0000-0000-0000-000000000001"),
        description="Hardcoded user_id until Auth.js comes online (Phase 12).",
    )


settings = Settings()  # type: ignore[call-arg]


def langgraph_dsn() -> str:
    """LangGraph Postgres checkpointer needs a sync psycopg DSN, not asyncpg."""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
