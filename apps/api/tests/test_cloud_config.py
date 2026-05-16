"""Phase 3 unit tests for the Supabase fields on Settings.

Verifies the contract that local-only setups boot without Supabase env vars
AND that real env values flow through pydantic-settings cleanly.
"""

from __future__ import annotations

import pytest
from foundry_api.config import Settings
from pydantic_settings import SettingsConfigDict


def _make_settings_class_without_env_file() -> type[Settings]:
    """Subclass that ignores the on-disk .env so tests stay hermetic."""

    class _IsolatedSettings(Settings):
        model_config = SettingsConfigDict(
            env_file=None,
            case_sensitive=False,
            extra="ignore",
        )

    return _IsolatedSettings


@pytest.mark.phase3
def test_settings_defaults_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — strip any Supabase env that the host shell happens to export
    for name in (
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_STORAGE_BUCKET",
    ):
        monkeypatch.delenv(name, raising=False)
    isolated = _make_settings_class_without_env_file()

    # Act
    s = isolated()  # type: ignore[call-arg]

    # Assert
    assert s.supabase_url is None
    assert s.supabase_anon_key is None
    assert s.supabase_service_role_key is None
    assert s.supabase_storage_bucket == "components"


@pytest.mark.phase3
def test_settings_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-xyz")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sb_secret_xyz")
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", "custom-bucket")
    isolated = _make_settings_class_without_env_file()

    # Act
    s = isolated()  # type: ignore[call-arg]

    # Assert
    assert s.supabase_url == "https://abc.supabase.co"
    assert s.supabase_anon_key == "anon-xyz"
    assert s.supabase_service_role_key == "sb_secret_xyz"
    assert s.supabase_storage_bucket == "custom-bucket"
