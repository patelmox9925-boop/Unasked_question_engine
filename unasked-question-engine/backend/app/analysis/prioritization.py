"""Transparent prioritisation.

    score = impact x likelihood x (0.80 + 0.02 x urgency)        range ~0.8 .. 100

* impact x likelihood is the classic risk-matrix product (1-100).
* urgency nudges the score by at most +/-10% around its midpoint (0.82 .. 1.00),
  so something merely "urgent" cannot outrank something severe and likely.

Levels: critical >= 60, high >= 36, medium >= 16, otherwise low.

All inputs are model-assigned judgements. The explanation attached to every
finding says so; scores are a ranking aid, not measurements.
"""

from __future__ import annotations

from ..schemas import EpistemicStatus, Finding, PriorityLevel, RiskSummary

URGENCY_BASE = 0.80
URGENCY_STEP = 0.02
THRESHOLDS: tuple[tuple[float, PriorityLevel], ...] = (
    (60.0, PriorityLevel.CRITICAL),
    (36.0, PriorityLevel.HIGH),
    (16.0, PriorityLevel.MEDIUM),
)
LEVEL_ORDER = [PriorityLevel.CRITICAL, PriorityLevel.HIGH, PriorityLevel.MEDIUM, PriorityLevel.LOW]

FORMULA_TEXT = (
    "priority score = impact × likelihood × (0.80 + 0.02 × urgency), on a scale of about 1–100. "
    "Levels: critical ≥ 60, high ≥ 36, medium ≥ 16, otherwise low. "
    "Impact, likelihood and urgency (1–10) are judgements made by the AI models, not measurements."
)


def urgency_factor(urgency: int) -> float:
    return URGENCY_BASE + URGENCY_STEP * urgency


def level_for(score: float) -> PriorityLevel:
    for threshold, level in THRESHOLDS:
        if score >= threshold:
            return level
    return PriorityLevel.LOW


def score_parts(impact: int, likelihood: int, urgency: int) -> tuple[float, PriorityLevel, str]:
    base = impact * likelihood
    factor = urgency_factor(urgency)
    score = round(base * factor, 1)
    explanation = (
        f"Impact {impact} × likelihood {likelihood} = {base}; urgency {urgency} applies a "
        f"×{factor:.2f} factor → {score:g}/100. These inputs are model judgements, not measurements."
    )
    return score, level_for(score), explanation


def prioritize(findings: list[Finding]) -> list[Finding]:
    """Set score/level/explanation on each finding and return them best-first."""
    for finding in findings:
        score, level, explanation = score_parts(finding.impact, finding.likelihood, finding.urgency)
        if finding.epistemic_status == EpistemicStatus.UNVERIFIED_HYPOTHESIS:
            explanation += " This item is an unverified hypothesis, so treat the ranking with extra caution."
        finding.priority_score, finding.priority_level, finding.score_explanation = score, level, explanation
    return sorted(findings, key=lambda f: (-(f.priority_score or 0), -f.impact, -f.likelihood, f.title.lower()))


def build_risk_summary(findings: list[Finding]) -> RiskSummary:
    counts = {level.value: 0 for level in LEVEL_ORDER}
    for f in findings:
        if f.priority_level:
            counts[f.priority_level.value] += 1
    overall = next((lvl for lvl in LEVEL_ORDER if counts[lvl.value] > 0), PriorityLevel.LOW)
    if not findings:
        explanation = "No findings were produced, so no risk level could be derived."
    else:
        parts = [f"{counts[l.value]} {l.value}" for l in LEVEL_ORDER if counts[l.value]]
        explanation = (
            f"Overall level is the highest priority level among the findings ({', '.join(parts)}). "
            "It reflects model-assigned scores; verify the top items before acting on them."
        )
    return RiskSummary(
        overall_level=overall,
        counts=counts,
        top_finding_ids=[f.id for f in findings[:5]],
        explanation=explanation,
        formula=FORMULA_TEXT,
    )
