"""Component Selection agent — Phase 3 foundation slice."""

from foundry_agent_component_selection.agent import ComponentSelectionAgent
from foundry_agent_component_selection.suppliers import (
    StubSupplierAdapter,
    SupplierAdapter,
)

__all__ = [
    "ComponentSelectionAgent",
    "StubSupplierAdapter",
    "SupplierAdapter",
]
