"""ProductState and all sub-schemas — single source of truth for the agent graph.

All datetimes are timezone-aware UTC. All monetary values are integer cents
to avoid float drift in cost ledger arithmetic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Conversation & requirements
# ---------------------------------------------------------------------------


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(BaseModel):
    role: MessageRole
    content: str
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Requirement(BaseModel):
    """One functional or non-functional requirement extracted by the Planner."""

    id: str
    statement: str
    category: Literal["functional", "constraint", "preference", "safety"]
    priority: Literal["must", "should", "nice-to-have"] = "must"


class Constraints(BaseModel):
    """Hard limits the product must satisfy."""

    max_dimensions_mm: tuple[float, float, float] | None = None
    max_weight_g: float | None = None
    max_power_w: float | None = None
    target_bom_cost_cents: int | None = None
    target_unit_count: int = 1
    compliance_markets: list[Literal["CN", "EU", "US"]] = Field(default_factory=list)


class ProductSpec(BaseModel):
    """Output of the Planner — frozen contract for downstream agents."""

    title: str
    summary: str
    requirements: list[Requirement]
    constraints: Constraints
    target_use_case: str
    frozen: bool = False


# ---------------------------------------------------------------------------
# Compliance (Phase 2 — Compliance agent)
# ---------------------------------------------------------------------------


class ComplianceTarget(BaseModel):
    """One regulation/standard that the product must (or should) satisfy."""

    market: Literal["CN", "EU", "US"]
    regulation: str
    clause_ref: str | None = None
    applies_because: str
    severity: Literal["mandatory", "recommended", "informational"]


class ComplianceReport(BaseModel):
    """Aggregate compliance findings for a ProductSpec."""

    targets: list[ComplianceTarget]
    summary: str


# ---------------------------------------------------------------------------
# Reference products (PR #4 — Reference Search agent)
# ---------------------------------------------------------------------------


class ReferenceProduct(BaseModel):
    """One similar product surfaced by Reference Search, with design notes."""

    name: str
    url: str
    summary: str
    design_takeaways: list[str] = Field(default_factory=list)
    similarity_score: float = Field(ge=0.0, le=1.0, default=0.5)


# ---------------------------------------------------------------------------
# Mechanical ⟷ Electrical contract
# ---------------------------------------------------------------------------


class Hole(BaseModel):
    x_mm: float
    y_mm: float
    diameter_mm: float
    purpose: Literal["mounting", "ventilation", "cable-pass", "connector"]


class ConnectorSlot(BaseModel):
    name: str
    position_mm: tuple[float, float]
    width_mm: float
    height_mm: float


class EnclosurePCBContract(BaseModel):
    """Bi-directional contract between CAD and PCB agents."""

    pcb_outline_mm: list[tuple[float, float]]
    pcb_thickness_max_mm: float = 1.6
    mounting_holes: list[Hole]
    component_height_zones: dict[str, float] = Field(default_factory=dict)
    connector_positions: list[ConnectorSlot] = Field(default_factory=list)
    last_modified_by: Literal["cad", "pcb"]
    last_modified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    revision: int = 0


# ---------------------------------------------------------------------------
# BOM
# ---------------------------------------------------------------------------


class BOMItem(BaseModel):
    designator: str | None = None
    mpn: str
    manufacturer: str
    description: str
    quantity: int = 1
    unit_price_cents: int
    supplier: Literal["digikey", "lcsc", "octopart", "jlcpcb", "other"] = "digikey"
    supplier_part_number: str | None = None
    in_stock: bool = True
    alternatives: list[str] = Field(default_factory=list)
    datasheet_url: str | None = None


class BOM(BaseModel):
    items: list[BOMItem]
    total_cost_cents: int
    currency: Literal["CNY", "USD", "EUR"] = "CNY"


# ---------------------------------------------------------------------------
# Artifacts produced by each design agent
# ---------------------------------------------------------------------------


class CADArtifacts(BaseModel):
    cadquery_source: str
    stl_path: str
    gcode_path: str | None = None
    render_paths: list[str] = Field(default_factory=list)
    dfam_report: dict[str, object] = Field(default_factory=dict)


class PCBArtifacts(BaseModel):
    kicad_project_path: str
    schematic_pdf_path: str | None = None
    gerber_zip_path: str | None = None
    drc_passed: bool = False
    erc_passed: bool = False


class SimResults(BaseModel):
    spice_netlist: str | None = None
    waveform_data_path: str | None = None
    thermal_report: dict[str, object] | None = None
    pass_fail: dict[str, bool] = Field(default_factory=dict)


class FirmwareArtifacts(BaseModel):
    platformio_project_path: str
    bin_path: str | None = None
    ble_services: list[dict[str, object]] = Field(default_factory=list)
    static_analysis_report: dict[str, object] | None = None


class AppArtifacts(BaseModel):
    expo_project_path: str
    eas_build_url: str | None = None
    apk_path: str | None = None
    ipa_path: str | None = None


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


CriticName = Literal["safety", "dfm", "cost", "ux", "reliability"]
Severity = Literal["block", "warn", "info"]


class Issue(BaseModel):
    severity: Severity
    location: str
    description: str
    suggestion: str | None = None
    cited_evidence: list[str] = Field(default_factory=list)


class CriticReport(BaseModel):
    critic_name: CriticName
    model_used: str
    severity: Severity
    issues: list[Issue]
    summary: str
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Fabrication
# ---------------------------------------------------------------------------


class FabOrder(BaseModel):
    vendor: Literal["jlcpcb", "pcbway", "jlc3dp", "octoprint_local", "digikey", "lcsc"]
    order_kind: Literal["pcb", "smt-assembly", "3d-print", "components"]
    artifact_refs: list[str]
    quote_cents: int | None = None
    tracking_id: str | None = None
    status: Literal[
        "draft", "awaiting-human", "submitted", "in-production", "shipped", "delivered"
    ] = "draft"
    submitted_at: datetime | None = None


# ---------------------------------------------------------------------------
# Documentation deliverables
# ---------------------------------------------------------------------------


class AssemblyDoc(BaseModel):
    pdf_path: str
    markdown: str
    exploded_view_paths: list[str] = Field(default_factory=list)
    wiring_diagram_path: str | None = None


class TestPlanDoc(BaseModel):
    pdf_path: str
    markdown: str
    cases: list[dict[str, object]] = Field(default_factory=list)


class UserManualDoc(BaseModel):
    pdf_path: str
    markdown: str
    troubleshooting_tree: dict[str, object] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Cross-cutting: cost ledger
# ---------------------------------------------------------------------------


class CostEvent(BaseModel):
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent: str
    delta_cents: int
    bucket: Literal["bom", "fab", "nre", "llm"]
    note: str = ""


class CostLedger(BaseModel):
    bom_cost_cents: int = 0
    fab_cost_cents: int = 0
    nre_cost_cents: int = 0
    llm_cost_cents: int = 0
    history: list[CostEvent] = Field(default_factory=list)

    @property
    def total_cents(self) -> int:
        return self.bom_cost_cents + self.fab_cost_cents + self.nre_cost_cents + self.llm_cost_cents


# ---------------------------------------------------------------------------
# Master state
# ---------------------------------------------------------------------------


PhaseLabel = Literal["clarify", "plan", "design", "review", "fab", "docs", "done"]


class ProductState(BaseModel):
    """Single shared state object for the entire LangGraph pipeline.

    Agents return a partial dict (StateUpdate) that LangGraph merges using
    reducers defined per field — they do not mutate this object directly.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    project_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    current_phase: PhaseLabel = "clarify"

    raw_input: str
    clarification_history: list[Message] = Field(default_factory=list)
    reference_findings: list[ReferenceProduct] | None = None
    product_spec: ProductSpec | None = None
    compliance_report: ComplianceReport | None = None

    bom: BOM | None = None
    cad_artifacts: CADArtifacts | None = None
    pcb_artifacts: PCBArtifacts | None = None
    sim_results: SimResults | None = None
    firmware_artifacts: FirmwareArtifacts | None = None
    app_artifacts: AppArtifacts | None = None

    enclosure_pcb_contract: EnclosurePCBContract | None = None

    review_reports: list[CriticReport] = Field(default_factory=list)
    review_decision: Literal["approve", "reject", "needs_revision"] | None = None

    fab_orders: list[FabOrder] = Field(default_factory=list)

    assembly_instructions: AssemblyDoc | None = None
    test_plan: TestPlanDoc | None = None
    user_manual: UserManualDoc | None = None

    cost_ledger: CostLedger = Field(default_factory=CostLedger)
    impact_set: set[str] = Field(default_factory=set)
    artifact_versions: dict[str, str] = Field(default_factory=dict)

    # User-driven signal: set True after user says "OK, start planning" via the
    # /commands/start-planning endpoint. Controls the conditional edge into Planner.
    user_intent_to_plan: bool = False

    # HITL gates — flipped by frontend after human approval
    gate_plan_approved: bool = False
    gate_review_approved: bool = False
    gate_fab_confirmed: bool = False
