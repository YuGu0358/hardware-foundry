"""Project entity — business-level container for a hardware design run.

Distinct from LangGraph's checkpoint tables (which store per-turn state).
A `Project` is what the user sees; the checkpoint is the engine state.
"""

from foundry_api.projects.models import Project
from foundry_api.projects.repository import ProjectRepository

__all__ = ["Project", "ProjectRepository"]
