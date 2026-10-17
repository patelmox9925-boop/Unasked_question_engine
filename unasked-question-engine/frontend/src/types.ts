export type Category =
  | "missing_assumption"
  | "overlooked_constraint"
  | "risk"
  | "missing_dependency"
  | "contradiction"
  | "missing_information"
  | "unasked_question"
  | "opportunity";

export type EpistemicStatus = "verified_fact" | "reasonable_inference" | "unverified_hypothesis";
export type PriorityLevel = "critical" | "high" | "medium" | "low";

export interface Evidence {
  kind: "cited" | "related";
  chunk_id: string;
  source_label: string;
  filename: string;
  excerpt: string;
  quote_verified: boolean;
}

export interface Finding {
  id: string;
  title: string;
  category: Category;
  perspective: string | null;
  explanation: string;
  why_it_matters: string;
  evidence: Evidence[];
  evidence_note: string | null;
  epistemic_status: EpistemicStatus;
  impact: number;
  likelihood: number;
  urgency: number;
  priority_score: number | null;
  priority_level: PriorityLevel | null;
  score_explanation: string | null;
  recommended_action: string;
  critical_question: string;
  why_overlooked: string | null;
  raised_by: string[];
  disagreement_note: string | null;
  origin: "llm" | "demo";
}

export interface RiskSummary {
  overall_level: PriorityLevel;
  counts: Record<PriorityLevel, number>;
  top_finding_ids: string[];
  explanation: string;
  formula: string;
}

export interface ModelConsulted {
  role: string;
  provider: string;
  model: string;
  succeeded: boolean;
  used_as_fallback: boolean;
}

export interface PerspectiveInfo {
  key: string;
  name: string;
  reason: string;
}

export interface ProjectFact {
  statement: string;
  kind: string;
  evidence: Evidence[];
}

export interface ProjectUnderstanding {
  summary: string;
  facts: ProjectFact[];
  open_items: string[];
}

export interface AnalysisResult {
  project_id: string;
  origin: "llm" | "demo";
  created_at: string;
  findings: Finding[];
  unanswered_questions: string[];
  overall_summary: string | null;
  understanding: ProjectUnderstanding | null;
  risk_summary: RiskSummary | null;
  perspectives: PerspectiveInfo[];
  models_consulted: ModelConsulted[];
  warnings: string[];
}

export type StepStatus = "pending" | "running" | "done" | "skipped" | "failed";

export interface AnalysisStep {
  key: string;
  label: string;
  status: StepStatus;
  detail: string | null;
}

export interface AnalysisStatus {
  project_id: string;
  state: "idle" | "running" | "done" | "failed";
  steps: AnalysisStep[];
  result: AnalysisResult | null;
  error: string | null;
}

export interface RejectedFile {
  filename: string;
  code: string;
  message: string;
}

export interface DocumentSummary {
  doc_id: string;
  filename: string;
  doc_type: string;
  char_count: number;
  chunk_count: number;
  warnings: string[];
  suspicious_chunks: number;
}

export interface ProjectResponse {
  project_id: string;
  created_at: string;
  has_description: boolean;
  documents: DocumentSummary[];
  rejected: RejectedFile[];
  total_chunks: number;
}

export interface RoleStatus {
  task: string;
  provider: string | null;
  model: string | null;
  primary_ready: boolean;
  fallback_provider: string | null;
  fallback_model: string | null;
  fallback_ready: boolean;
}

export type ProviderName = "gemini" | "groq" | "deepseek";
export type RoleKey = "A" | "B" | "C";

export interface ProviderStatus {
  api_key_configured: boolean;
  key_hint?: string | null;
  label?: string;
  key_url?: string;
  strengths?: string;
  default_role?: RoleKey;
  suggested_models?: string[];
}

export interface ConfigStatus {
  environment: string;
  limits: { max_upload_mb: number; max_files: number; max_description_chars: number };
  providers: Record<string, ProviderStatus>;
  roles: Record<"A" | "B" | "C", RoleStatus>;
  live_analysis_available: boolean;
  all_roles_ready: boolean;
}

export type Grounding = "grounded" | "partly_grounded" | "not_in_material";

export interface ChatResponse {
  answer: string;
  grounding: Grounding;
  evidence: Evidence[];
  finding_ids: string[];
  follow_ups?: string[];
  model: ModelConsulted;
  warnings: string[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export type TriageStatus = "open" | "accepted" | "dismissed" | "resolved";

export interface TriageEntry {
  status: TriageStatus;
  note: string;
}

export interface ChunkResponse {
  chunk_id: string;
  doc_id: string;
  text: string;
  source_label: string;
  kind: string;
  flags: string[];
}

export interface RoleSettings {
  provider: string;
  model: string;
  fallback_provider: string;
  fallback_model: string;
}

export interface SettingsUpdate {
  roles?: Partial<Record<RoleKey, RoleSettings>>;
  keys?: Record<string, string | null>;
}

export interface ConnectionTest {
  ok: boolean;
  stage: "key" | "model";
  message: string;
  models: string[];
}
