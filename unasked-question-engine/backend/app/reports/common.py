"""Shared helpers for the report builders."""

from __future__ import annotations

import re
from datetime import datetime

from ..schemas import AnalysisResult, EpistemicStatus, Evidence, Finding

CATEGORY_LABELS = {
    "missing_assumption": "Missing assumption",
    "overlooked_constraint": "Overlooked constraint",
    "risk": "Risk",
    "missing_dependency": "Missing dependency",
    "contradiction": "Contradiction",
    "missing_information": "Missing information",
    "unasked_question": "Unasked question",
    "opportunity": "Opportunity",
}
STATUS_LABELS = {
    EpistemicStatus.VERIFIED_FACT: "Stated in the material",
    EpistemicStatus.REASONABLE_INFERENCE: "Inferred from the material",
    EpistemicStatus.UNVERIFIED_HYPOTHESIS: "Unverified hypothesis",
}
DEMO_NOTICE = (
    "DEMO DATA: this report was produced from predefined sample results, not by an AI model. "
    "It is shown only to demonstrate the product and says nothing about real documents."
)
GENERAL_NOTICE = (
    "AI-generated analysis. Scores are model judgements, not measurements. Check the cited evidence "
    "before acting, and consult a qualified professional for legal, financial or security decisions."
)


def category_label(finding: Finding) -> str:
    return CATEGORY_LABELS.get(finding.category.value, finding.category.value)


def level_label(finding: Finding) -> str:
    level = finding.priority_level.value.capitalize() if finding.priority_level else "Unranked"
    score = f" {finding.priority_score:g}" if finding.priority_score is not None else ""
    return f"{level}{score}"


def one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def evidence_location(ev: Evidence) -> str:
    return ev.source_label


def evidence_check(ev: Evidence) -> str:
    if ev.kind == "related":
        return "closest passage found by search; the model did not cite it"
    return "exact quote verified in source" if ev.quote_verified else "excerpt shown for context, not a verified quote"


def timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M UTC")


def is_demo(result: AnalysisResult) -> bool:
    return result.origin == "demo" or any(f.origin == "demo" for f in result.findings)


def models_line(result: AnalysisResult) -> list[str]:
    if is_demo(result):
        return ["No AI model was consulted (demo data)."]
    if not result.models_consulted:
        return ["No model information was recorded."]
    rows = []
    for m in result.models_consulted:
        state = "completed" if m.succeeded else "FAILED"
        fallback = ", fallback provider" if m.used_as_fallback else ""
        rows.append(f"Model {m.role}: {m.provider} / {m.model} ({state}{fallback})")
    return rows


TRIAGE_LABELS = {"open": "Open", "accepted": "Accepted: needs action", "dismissed": "Dismissed", "resolved": "Resolved"}


def triage_line(entry) -> str | None:
    """"Accepted: needs action. Note: ..." or None when nothing was decided."""
    if entry is None or (entry.status == "open" and not entry.note):
        return None
    text = TRIAGE_LABELS[entry.status]
    return f"{text}. Note: {one_line(entry.note)}" if entry.note else text


def triage_counts(triage: dict) -> str | None:
    counts = {k: sum(1 for e in triage.values() if e.status == k) for k in ("accepted", "dismissed", "resolved")}
    if not any(counts.values()):
        return None
    return ", ".join(f"{n} {k}" for k, n in counts.items() if n)
