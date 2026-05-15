"""Supplier adapter protocol + stub implementation.

Real Digi-Key / LCSC / Octopart adapters land in follow-up PRs. This stub
is what runs in CI and on developer laptops without API credentials.
"""

from __future__ import annotations

import re
from typing import ClassVar, Protocol

from foundry_agent_base import ComponentMatch, ComponentQuery

# Deterministic price points (cents) for the 3 stub candidates, ordered by rank.
_STUB_PRICES_CENTS: tuple[int, int, int] = (100, 250, 800)
# Deterministic self-reported fit scores for ranks 1/2/3.
_STUB_SCORES: tuple[float, float, float] = (0.9, 0.7, 0.5)
# Number of candidates returned per stub query (matches the API contract).
_STUB_CANDIDATE_COUNT = 3


def _slug(value: str) -> str:
    """Lower-case slug with non-alphanumerics collapsed to single dashes."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned or "part"


class SupplierAdapter(Protocol):
    """Interface every supplier integration must satisfy."""

    name: str

    async def search(self, query: ComponentQuery) -> list[ComponentMatch]: ...


class StubSupplierAdapter:
    """Returns 3 deterministic fake matches per query.

    Used in dev/CI when no supplier API keys are configured. No randomness,
    no time-dependent behavior — same input always yields the same output.
    """

    name: ClassVar[str] = "stub"

    async def search(self, query: ComponentQuery) -> list[ComponentMatch]:
        role_slug = _slug(query.role)
        return [
            ComponentMatch(
                mpn=f"STUB-{role_slug}-{i + 1}",
                manufacturer=f"StubMfg{i + 1}",
                description=f"Stub candidate {i + 1} for role '{query.role}'",
                supplier="stub",
                supplier_part_number=f"STUB-SPN-{role_slug}-{i + 1}",
                unit_price_cents=_STUB_PRICES_CENTS[i],
                in_stock=True,
                moq=1,
                datasheet_url=None,
                parametric=dict(query.parameters),
                score=_STUB_SCORES[i],
            )
            for i in range(_STUB_CANDIDATE_COUNT)
        ]
