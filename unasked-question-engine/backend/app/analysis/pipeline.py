"""Input -> Extraction -> Context -> A analysis -> B critique -> C synthesis -> Prioritisation.

Honesty rules enforced here:
* Model A is required. If it fails everywhere, ``AnalysisFailed`` is raised and
  *no analysis is fabricated*.
* B and C are used only when configured. Their failure degrades the result and
  adds a visible warning; it never silently pretends they ran.
* ``models_consulted`` is built from the router's recorded attempts, so a model
  whose call failed is listed with ``succeeded=False`` and never as consulted.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from ..providers.router import Attempt, AllProvidersFailed, LLMRouter
from ..schemas import (
    AnalysisOutput,
    AnalysisResult,
    CritiqueOutput,
    FactSheet,
    Finding,
    ModelConsulted,
    ProjectFact,
    ProjectUnderstanding,
    RawFinding,
    StepStatus,
    SynthesisOutput,
)
from ..store import Project
from .checklists import detect_domains
from .context import build_context
from .quality import attach_related_evidence, calibration_warning, drop_generic
from .merge import dedupe_findings, match_title, resolve_evidence, to_finding
from .perspectives import select_perspectives
from .prioritization import build_risk_summary, prioritize
from .prompts import analyst_request, critic_request, facts_request, synthesis_request

logger = logging.getLogger(__name__)

MAX_FINDINGS = 40
MAX_DERIVED_QUESTIONS = 8
MAX_CANDIDATES_TO_SYNTHESIS = 28

STEP_LABELS: list[tuple[str, str]] = [
    ("extract", "Reading documents"),
    ("context", "Choosing perspectives"),
    ("facts", "Understanding the project (Model A)"),
    ("analysis", "Hunting for gaps (Model A)"),
    ("critique", "Independent critique (Model B)"),
    ("synthesis", "Validation and synthesis (Model C)"),
    ("prioritize", "Prioritizing findings"),
]

ProgressFn = Callable[[str, StepStatus, str | None], None]


class AnalysisFailed(Exception):
    def __init__(self, message: str, models: list[ModelConsulted]):
        super().__init__(message)
        self.message = message
        self.models = models


def consulted_from(attempts: list[Attempt]) -> list[ModelConsulted]:
    seen: set[tuple] = set()
    out: list[ModelConsulted] = []
    for a in attempts:
        key = (a.role, a.provider, a.model, a.ok)
        if key in seen:
            continue
        seen.add(key)
        out.append(ModelConsulted(role=a.role, provider=a.provider, model=a.model,
                                  succeeded=a.ok, used_as_fallback=a.is_fallback))
    return out


def _dedupe_models(models: list[ModelConsulted]) -> list[ModelConsulted]:
    """One line per role/provider/model/outcome, even when a role made several calls (fact sheet + analysis)."""
    seen: set[tuple] = set()
    out: list[ModelConsulted] = []
    for m in models:
        key = (m.role, m.provider, m.model, m.succeeded, m.used_as_fallback)
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = " ".join(item.lower().split())
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def _candidate_dict(raw: RawFinding, source: str) -> dict[str, Any]:
    data = raw.model_dump(mode="json")
    data["raised_by"] = source
    return data


class AnalysisPipeline:
    def __init__(self, router: LLMRouter):
        self.router = router

    async def run(self, project: Project, on_progress: ProgressFn | None = None) -> AnalysisResult:
        progress: ProgressFn = on_progress or (lambda *_: None)
        warnings: list[str] = []
        consulted: list[ModelConsulted] = []

        # ---- extraction + context
        chunks = project.chunks
        progress("extract", "done", f"{len(chunks)} sections from {len(project.documents)} source(s)")
        selected = select_perspectives(chunks)
        perspective_objs = [p for p, _ in selected]
        domains = detect_domains(chunks)
        settings = self.router.settings

        def context_for(role: str):
            """Each role sees as much material as its provider accepts (small models see less)."""
            return build_context(chunks, perspective_objs, settings.context_budget_for_role(role))

        context = context_for("A")
        warnings.extend(context.warnings)
        perspectives = [info for _, info in selected]
        kinds = ", ".join(d.name for d in domains)
        progress("context", "done", ", ".join(i.name for i in perspectives) + (f". Project type: {kinds}." if kinds else ""))
        chunk_map = project.chunk_map()

        # ---- Model A, pass 1: what does the material actually say?
        progress("facts", "running", None)
        facts: FactSheet | None = None
        try:
            fr = await self.router.run("A", facts_request(context), FactSheet)
            facts = fr.data
            consulted += consulted_from(fr.attempts)
            progress("facts", "done", f"{len(facts.facts)} facts noted by {fr.provider}/{fr.model}")
        except AllProvidersFailed as exc:
            only_schema = bool(exc.attempts) and all(a.error_kind == "invalid_response" for a in exc.attempts)
            if not only_schema:  # outage, bad key, rate limit: the analysis step would fail the same way
                progress("facts", "failed", exc.message)
                raise AnalysisFailed(exc.message, consulted_from(exc.attempts)) from exc
            consulted += consulted_from(exc.attempts)
            warnings.append("The fact-sheet step could not be completed, so the gap analysis ran without it.")
            progress("facts", "skipped", "The model's fact sheet was unusable; continuing without it.")

        # ---- Model A (required)
        progress("analysis", "running", None)
        try:
            a = await self.router.run("A", analyst_request(context, facts, domains), AnalysisOutput)
        except AllProvidersFailed as exc:
            progress("analysis", "failed", exc.message)
            raise AnalysisFailed(exc.message, consulted_from(exc.attempts)) from exc
        consulted += consulted_from(a.attempts)
        a_label = f"A ({a.provider}/{a.model})"
        progress("analysis", "done", f"{len(a.data.findings)} candidate findings from {a.provider}/{a.model}")
        candidates: list[tuple[RawFinding, str]] = [(f, a_label) for f in a.data.findings]

        # ---- Model B (optional)
        critique: CritiqueOutput | None = None
        b_label = ""
        if self.router.role_available("B"):
            progress("critique", "running", None)
            try:
                b = await self.router.run(
                    "B", critic_request(context_for("B"), [_candidate_dict(r, l) for r, l in candidates]),
                    CritiqueOutput)
                critique = b.data
                b_label = f"B ({b.provider}/{b.model})"
                consulted += consulted_from(b.attempts)
                candidates += [(f, b_label) for f in critique.missed_findings]
                progress("critique", "done",
                         f"{len(critique.challenges)} challenges, {len(critique.missed_findings)} missed findings "
                         f"from {b.provider}/{b.model}")
            except AllProvidersFailed as exc:
                consulted += consulted_from(exc.attempts)
                warnings.append(f"Independent critique (Model B) was unavailable: {exc.message}")
                progress("critique", "failed", exc.message)
        else:
            progress("critique", "skipped", "Model B is not configured.")

        # ---- Model C (optional)
        synthesis: SynthesisOutput | None = None
        c_label = ""
        synth_note = "Model C is not configured."
        if not candidates and not (critique and critique.missing_questions):
            progress("synthesis", "skipped", "Nothing to synthesise.")
            synth_note = "There was nothing to synthesise."
        elif self.router.role_available("C"):
            progress("synthesis", "running", None)
            try:
                top = sorted(candidates, key=lambda t: -(t[0].impact * t[0].likelihood))[:MAX_CANDIDATES_TO_SYNTHESIS]
                c = await self.router.run(
                    "C",
                    synthesis_request(
                        context_for("C"),
                        [_candidate_dict(r, l) for r, l in top],
                        [ch.model_dump(mode="json") for ch in (critique.challenges if critique else [])],
                        critique.missing_questions if critique else [],
                    ),
                    SynthesisOutput)
                synthesis = c.data
                c_label = f"C ({c.provider}/{c.model})"
                consulted += consulted_from(c.attempts)
                progress("synthesis", "done", f"{len(synthesis.findings)} findings after validation by "
                                              f"{c.provider}/{c.model}")
            except AllProvidersFailed as exc:
                consulted += consulted_from(exc.attempts)
                synth_note = f"Model C failed: {exc.message}"
                warnings.append(f"Validation and synthesis (Model C) was unavailable: {exc.message}")
                progress("synthesis", "failed", exc.message)
        else:
            progress("synthesis", "skipped", "Model C is not configured.")

        # ---- build findings
        progress("prioritize", "running", None)
        if synthesis is not None:
            findings = self._from_synthesis(synthesis, candidates, chunk_map, c_label, warnings)
            questions = _unique(synthesis.unanswered_questions) or _unique(
                critique.missing_questions if critique else [])
            summary = synthesis.overall_summary
        else:
            warnings.append(
                f"{synth_note} Findings were de-duplicated and evidence-checked by deterministic rules only, "
                "without an independent validation pass.")
            findings = [to_finding(raw, chunk_map, raised_by=[label]) for raw, label in candidates]
            if critique:
                self._apply_challenges(findings, critique, b_label)
            findings = dedupe_findings(findings)
            summary = None
            questions = []  # filled below, after ranking

        findings = dedupe_findings(findings)
        findings, dropped = drop_generic(findings, chunks)
        if dropped:
            warnings.append(f"{dropped} finding(s) were removed because they were generic: no supporting text "
                            "and nothing specific to this material.")
        findings = findings[:MAX_FINDINGS]
        attach_related_evidence(findings, chunks)
        findings = prioritize(findings)
        note = calibration_warning(findings)
        if note:
            warnings.append(note)
        for index, finding in enumerate(findings, start=1):
            finding.id = f"f{index}"
        if synthesis is None:
            derived = (critique.missing_questions if critique else []) + [
                f.critical_question for f in findings[:MAX_DERIVED_QUESTIONS]]
            questions = _unique(derived)
        if not findings:
            warnings.append("The models reported no findings for this material.")
        progress("prioritize", "done", f"{len(findings)} findings ranked")

        return AnalysisResult(
            project_id=project.project_id,
            origin="llm",
            created_at=datetime.now(timezone.utc),
            findings=findings,
            unanswered_questions=questions,
            overall_summary=summary,
            understanding=self._understanding(facts, chunk_map),
            risk_summary=build_risk_summary(findings),
            perspectives=perspectives,
            models_consulted=_dedupe_models(consulted),
            warnings=warnings,
        )

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _understanding(facts: FactSheet | None, chunk_map: dict) -> ProjectUnderstanding | None:
        if facts is None:
            return None
        return ProjectUnderstanding(
            summary=facts.project_summary,
            facts=[ProjectFact(statement=f.statement, kind=f.kind, evidence=resolve_evidence(f.citations, chunk_map))
                   for f in facts.facts],
            open_items=list(facts.open_items),
        )

    @staticmethod
    def _apply_challenges(findings: list[Finding], critique: CritiqueOutput, label: str) -> None:
        by_title = {f.title: f for f in findings}
        for challenge in critique.challenges:
            key = match_title(challenge.finding_title, by_title)
            if key is None:
                continue
            target = by_title[key]
            note = f"Reviewer {label} objected: {challenge.objection}"
            target.disagreement_note = f"{target.disagreement_note} {note}".strip() if target.disagreement_note else note

    @staticmethod
    def _from_synthesis(synthesis: SynthesisOutput, candidates: list[tuple[RawFinding, str]],
                        chunk_map: dict, c_label: str, warnings: list[str]) -> list[Finding]:
        by_title: dict[str, tuple[RawFinding, str]] = {}
        for raw, label in candidates:
            by_title.setdefault(raw.title, (raw, label))
        introduced = 0
        findings: list[Finding] = []
        for sf in synthesis.findings:
            keys = {k for name in (sf.title, *sf.merged_from) if (k := match_title(name, by_title))}
            labels = list(dict.fromkeys(by_title[k][1] for k in keys))
            inherited = [cit for k in keys for cit in by_title[k][0].citations]
            if not keys:
                introduced += 1
            findings.append(to_finding(sf, chunk_map, raised_by=[*labels, c_label],
                                       extra_citations=inherited))
        if introduced:
            warnings.append(f"{introduced} finding(s) first appeared in the synthesis step rather than in the "
                            "initial analysis or critique; their evidence was checked in the same way.")
        return findings
