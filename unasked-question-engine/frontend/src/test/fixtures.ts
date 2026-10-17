import type { AnalysisResult, ConfigStatus, Finding } from "../types";

export function makeFinding(over: Partial<Finding> = {}): Finding {
  return {
    id: "f1",
    title: "Shared password is the only login control",
    category: "risk",
    perspective: "security",
    explanation: "Users log in with a shared password.",
    why_it_matters: "Shared credentials cannot be revoked per person.",
    evidence: [
      {
        kind: "cited",
        chunk_id: "desc-c1",
        source_label: 'Project description, section "Plan", line 4',
        filename: "Project description",
        excerpt: "Users log in with a shared password",
        quote_verified: true,
      },
    ],
    evidence_note: null,
    epistemic_status: "verified_fact",
    impact: 9,
    likelihood: 8,
    urgency: 8,
    priority_score: 70.6,
    priority_level: "critical",
    score_explanation: "Impact 9 × likelihood 8 = 72; urgency 8 applies a ×0.96 factor → 69.1/100.",
    recommended_action: "Introduce individual accounts.",
    critical_question: "How will access be revoked when someone leaves?",
    why_overlooked: null,
    raised_by: ["A (groq/model-a)"],
    disagreement_note: null,
    origin: "llm",
    ...over,
  };
}

export const FINDINGS: Finding[] = [
  makeFinding(),
  makeFinding({
    id: "f2",
    title: "Hosting cost is capped but traffic is unknown",
    category: "missing_assumption",
    evidence: [],
    evidence_note: "Not directly evidenced: this is based on what the provided material does not say.",
    epistemic_status: "reasonable_inference",
    impact: 7,
    likelihood: 6,
    urgency: 5,
    priority_score: 40.6,
    priority_level: "high",
    critical_question: "What usage makes the cap insufficient?",
  }),
  makeFinding({
    id: "f3",
    title: "Vendor lock-in is possible",
    category: "overlooked_constraint",
    evidence: [],
    evidence_note: "No supporting text was found in the provided material for this item; treat it as unverified.",
    epistemic_status: "unverified_hypothesis",
    impact: 3,
    likelihood: 3,
    urgency: 2,
    priority_score: 8,
    priority_level: "low",
    critical_question: "Can we leave this vendor within a quarter?",
  }),
];

export function makeResult(over: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    project_id: "p1",
    origin: "llm",
    created_at: "2026-10-17T08:00:00Z",
    findings: FINDINGS,
    unanswered_questions: ["Who is on call after launch?"],
    overall_summary: "Access control and cost are the main blind spots.",
    understanding: null,
    risk_summary: {
      overall_level: "critical",
      counts: { critical: 1, high: 1, medium: 0, low: 1 },
      top_finding_ids: ["f1", "f2", "f3"],
      explanation: "Overall level is the highest priority level among the findings (1 critical, 1 high, 1 low).",
      formula: "priority score = impact × likelihood × (0.80 + 0.02 × urgency)",
    },
    perspectives: [{ key: "security", name: "Security and privacy", reason: "The material mentions: password." }],
    models_consulted: [
      { role: "A", provider: "groq", model: "model-a", succeeded: true, used_as_fallback: false },
      { role: "B", provider: "deepseek", model: "model-b", succeeded: false, used_as_fallback: false },
    ],
    warnings: ["Independent critique (Model B) was unavailable: deepseek/model-b: auth."],
    ...over,
  };
}

export function makeConfig(live = true): ConfigStatus {
  const role = (task: string, ready: boolean) => ({
    task,
    provider: ready ? "groq" : null,
    model: ready ? "model-a" : null,
    primary_ready: ready,
    fallback_provider: null,
    fallback_model: null,
    fallback_ready: false,
  });
  return {
    environment: "test",
    limits: { max_upload_mb: 1, max_files: 3, max_description_chars: 100 },
    providers: { groq: { api_key_configured: live }, gemini: { api_key_configured: false }, deepseek: { api_key_configured: false } },
    roles: { A: role("Initial analysis", live), B: role("Critique", false), C: role("Synthesis", false) },
    live_analysis_available: live,
    all_roles_ready: false,
  };
}
