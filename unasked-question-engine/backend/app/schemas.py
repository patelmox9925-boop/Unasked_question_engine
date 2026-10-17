"""Pydantic schemas.

Three groups:

* LLM-facing output models (``RawFinding`` etc.). These are *strict*
  (``extra="forbid"``). Models may only cite evidence by ``chunk_id``; the backend
  resolves the real source location, so evidence locations can never be invented.
* Final domain models (``Evidence``, ``Finding``, ``AnalysisResult``).
* API request/response models.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2500)]
MidText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Score = Annotated[int, Field(ge=1, le=10)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Category(str, Enum):
    MISSING_ASSUMPTION = "missing_assumption"
    OVERLOOKED_CONSTRAINT = "overlooked_constraint"
    RISK = "risk"
    MISSING_DEPENDENCY = "missing_dependency"
    CONTRADICTION = "contradiction"
    MISSING_INFORMATION = "missing_information"
    UNASKED_QUESTION = "unasked_question"
    OPPORTUNITY = "opportunity"


class EpistemicStatus(str, Enum):
    VERIFIED_FACT = "verified_fact"  # directly stated in the provided material
    REASONABLE_INFERENCE = "reasonable_inference"  # follows from the material
    UNVERIFIED_HYPOTHESIS = "unverified_hypothesis"  # plausible, not supported by the material


class PriorityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# --------------------------------------------------------------------------- LLM output
class EvidenceCitation(StrictModel):
    chunk_id: ShortText
    quote: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class RawFinding(StrictModel):
    title: ShortText
    category: Category
    perspective: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None
    explanation: LongText
    why_it_matters: LongText
    citations: list[EvidenceCitation] = Field(default_factory=list, max_length=6)
    epistemic_status: EpistemicStatus
    impact: Score
    likelihood: Score
    urgency: Score
    recommended_action: LongText
    critical_question: MidText
    why_overlooked: MidText | None = None  # why a team is likely to miss this


FactKind = Literal["goal", "commitment", "number", "date", "dependency", "assumption", "decision",
                   "constraint", "data", "other"]


class RawFact(StrictModel):
    statement: MidText
    kind: FactKind = "other"
    citations: list[EvidenceCitation] = Field(default_factory=list, max_length=3)


class FactSheet(StrictModel):
    """Role A, pass 1: what the material actually says, before looking for gaps."""

    project_summary: LongText
    facts: list[RawFact] = Field(max_length=60)
    open_items: list[MidText] = Field(default_factory=list, max_length=15)  # things the material itself leaves TBD


class AnalysisOutput(StrictModel):
    """Role A output."""

    findings: list[RawFinding] = Field(max_length=40)


class Challenge(StrictModel):
    finding_title: ShortText
    objection: LongText
    suggested_adjustment: MidText | None = None


class CritiqueOutput(StrictModel):
    """Role B output."""

    challenges: list[Challenge] = Field(default_factory=list, max_length=40)
    missed_findings: list[RawFinding] = Field(default_factory=list, max_length=20)
    missing_questions: list[MidText] = Field(default_factory=list, max_length=20)


class SynthesizedFinding(RawFinding):
    merged_from: list[ShortText] = Field(default_factory=list, max_length=20)
    disagreement_note: MidText | None = None
    validation_note: MidText | None = None


class SynthesisOutput(StrictModel):
    """Role C output."""

    findings: list[SynthesizedFinding] = Field(max_length=40)
    unanswered_questions: list[MidText] = Field(default_factory=list, max_length=25)
    overall_summary: LongText


# --------------------------------------------------------------------------- domain
class Evidence(BaseModel):
    kind: Literal["cited", "related"] = "cited"  # "related" = found by search, not cited by a model
    chunk_id: str
    source_label: str
    filename: str
    page: int | None = None
    heading: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    excerpt: str
    quote_verified: bool = Field(
        description="True only if the excerpt is an exact quote found in the source chunk."
    )


class ModelConsulted(BaseModel):
    role: str
    provider: str
    model: str
    succeeded: bool
    used_as_fallback: bool = False


class Finding(BaseModel):
    id: str
    title: str
    category: Category
    perspective: str | None = None
    explanation: str
    why_it_matters: str
    evidence: list[Evidence] = Field(default_factory=list)
    evidence_note: str | None = None  # set when no document evidence is available
    epistemic_status: EpistemicStatus
    impact: int
    likelihood: int
    urgency: int
    priority_score: float | None = None
    priority_level: PriorityLevel | None = None
    score_explanation: str | None = None
    recommended_action: str
    critical_question: str
    why_overlooked: str | None = None
    raised_by: list[str] = Field(default_factory=list)
    disagreement_note: str | None = None
    origin: Literal["llm", "demo"] = "llm"


class PerspectiveInfo(BaseModel):
    key: str
    name: str
    reason: str


class RiskSummary(BaseModel):
    overall_level: PriorityLevel
    counts: dict[str, int]
    top_finding_ids: list[str]
    explanation: str
    formula: str


class ProjectFact(BaseModel):
    statement: str
    kind: str
    evidence: list[Evidence] = Field(default_factory=list)


class ProjectUnderstanding(BaseModel):
    """What the engine understood the material to say (shown so users can spot misreadings)."""

    summary: str
    facts: list[ProjectFact] = Field(default_factory=list)
    open_items: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    project_id: str
    origin: Literal["llm", "demo"] = "llm"
    created_at: datetime
    findings: list[Finding] = Field(default_factory=list)
    unanswered_questions: list[str] = Field(default_factory=list)
    overall_summary: str | None = None
    understanding: ProjectUnderstanding | None = None
    risk_summary: RiskSummary | None = None
    perspectives: list[PerspectiveInfo] = Field(default_factory=list)
    models_consulted: list[ModelConsulted] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


StepStatus = Literal["pending", "running", "done", "skipped", "failed"]


class AnalysisStep(BaseModel):
    key: str
    label: str
    status: StepStatus = "pending"
    detail: str | None = None


class AnalysisStatus(BaseModel):
    project_id: str
    state: Literal["idle", "running", "done", "failed"]
    steps: list[AnalysisStep] = Field(default_factory=list)
    result: AnalysisResult | None = None
    error: str | None = None


# --------------------------------------------------------------------------- triage
TriageStatus = Literal["open", "accepted", "dismissed", "resolved"]


class TriageEntry(BaseModel):
    status: TriageStatus = "open"
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""


# --------------------------------------------------------------------------- chat
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class ChatRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    history: list[ChatMessage] = Field(default_factory=list, max_length=10)


GroundingLevel = Literal["grounded", "partly_grounded", "not_in_material"]


class ChatOutput(StrictModel):
    """LLM output for follow-up questions."""

    answer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)]
    citations: list[EvidenceCitation] = Field(default_factory=list, max_length=8)
    finding_ids: list[ShortText] = Field(default_factory=list, max_length=10)
    grounding: GroundingLevel
    follow_ups: list[MidText] = Field(default_factory=list, max_length=4)


class ChatResponse(BaseModel):
    answer: str
    grounding: GroundingLevel
    evidence: list[Evidence] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    model: ModelConsulted
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- API
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class RejectedFile(BaseModel):
    filename: str
    code: str
    message: str


class DocumentSummary(BaseModel):
    doc_id: str
    filename: str
    doc_type: str
    char_count: int
    chunk_count: int
    warnings: list[str] = Field(default_factory=list)
    suspicious_chunks: int = 0


class ProjectResponse(BaseModel):
    project_id: str
    created_at: datetime
    has_description: bool
    documents: list[DocumentSummary]
    rejected: list[RejectedFile] = Field(default_factory=list)
    total_chunks: int


class ChunkResponse(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    source_label: str
    kind: str
    flags: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
