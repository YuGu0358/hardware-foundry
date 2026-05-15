// Mirrors a subset of foundry_agent_base.state Pydantic schemas.
// Manually maintained for now; Phase 12 will auto-generate from OpenAPI.

export type Phase = "clarify" | "plan" | "design" | "review" | "fab" | "docs" | "done";

export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  at: string; // ISO-8601
}

export interface ReferenceProduct {
  name: string;
  url: string;
  summary: string;
  design_takeaways: string[];
  similarity_score: number;
}

export interface Requirement {
  id: string;
  statement: string;
  category: "functional" | "constraint" | "preference" | "safety";
  priority: "must" | "should" | "nice-to-have";
}

export interface Constraints {
  max_dimensions_mm: [number, number, number] | null;
  max_weight_g: number | null;
  max_power_w: number | null;
  target_bom_cost_cents: number | null;
  target_unit_count: number;
  compliance_markets: Array<"CN" | "EU" | "US">;
}

export interface ProductSpec {
  title: string;
  summary: string;
  requirements: Requirement[];
  constraints: Constraints;
  target_use_case: string;
  frozen: boolean;
}

export interface ProductStateLike {
  run_id: string;
  user_id: string;
  project_id: string;
  current_phase: Phase;
  raw_input: string;
  clarification_history: Message[];
  reference_findings: ReferenceProduct[] | null;
  product_spec: ProductSpec | null;
  user_intent_to_plan: boolean;
  gate_plan_approved: boolean;
}

export interface ProjectSummary {
  id: string;
  title: string | null;
  current_phase: Phase;
  raw_input: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail {
  project: ProjectSummary;
  state: ProductStateLike;
}
