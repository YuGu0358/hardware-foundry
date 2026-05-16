"""Phase 3 unit tests for the components+pgvector Alembic migration.

We don't run the migration here (that needs a live DB and is the
orchestrator's job). Instead we verify the module is well-formed so a typo
in revision wiring can't slip through review.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations" / "versions"


@pytest.mark.phase3
def test_migration_module_loads() -> None:
    # Arrange — load by file path so we don't need a package __init__ in versions/
    module_path = _MIGRATIONS_DIR / "0002_components_pgvector.py"
    assert module_path.is_file(), f"missing migration file at {module_path}"
    spec = importlib.util.spec_from_file_location(
        "migrations_0002_components_pgvector", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    # Act
    spec.loader.exec_module(module)

    # Assert — revision wiring must match the chain Alembic expects.
    assert module.revision == "0002_components_pgvector"
    assert module.down_revision == "0001_init_projects"
    assert module.branch_labels is None
    assert module.depends_on is None
    assert callable(module.upgrade)
    assert callable(module.downgrade)
