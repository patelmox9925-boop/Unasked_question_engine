"""Markdown report. Model text is treated as data: raw HTML is neutralised."""

from __future__ import annotations

import re

from ..schemas import AnalysisResult, Finding
from . import common as c


def _safe(text: str) -> str:
    """Neutralise raw HTML and images so a viewer cannot be made to load remote content."""
    text = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"!\[", r"!\\[", text)


def _quote(text: str) -> str:
    lines = _safe(text).strip().splitlines() or [""]
    return "\n".join(f"> {line}".rstrip() for line in lines)


def _finding(rank: int, f: Finding, triage=None) -> list[str]:
    out = [
        f"### {rank}. {_safe(c.one_line(f.title))}",
        "",
        f"**{c.level_label(f)}** · {c.category_label(f)} · {c.STATUS_LABELS[f.epistemic_status]}"
        + (" · demo data" if f.origin == "demo" else ""),
        "",
        _safe(f.explanation),
        "",
        f"**Why it matters.** {_safe(f.why_it_matters)}",
        "",
        *([f"**Why it is easy to miss.** {_safe(f.why_overlooked)}", ""] if f.why_overlooked else []),
        f"**Recommended action.** {_safe(f.recommended_action)}",
        "",
        f"**Question to answer:** {_safe(f.critical_question)}",
        "",
        f"Scores: impact {f.impact}/10, likelihood {f.likelihood}/10, urgency {f.urgency}/10. "
        f"{_safe(f.score_explanation or '')}",
        "",
    ]
    decision = c.triage_line((triage or {}).get(f.id))
    if decision:
        out += [f"**Your decision:** {_safe(decision)}", ""]
    if f.perspective:
        out += [f"Perspective: {_safe(f.perspective)}", ""]
    if f.disagreement_note:
        out += [f"**Models disagreed.** {_safe(f.disagreement_note)}", ""]
    if f.evidence:
        out += ["**Evidence**", ""]
        for ev in f.evidence:
            out += [_quote(ev.excerpt), f"> — {_safe(c.evidence_location(ev))} ({c.evidence_check(ev)})", ""]
    else:
        out += [f"*No document evidence.* {_safe(f.evidence_note or 'Nothing in the material directly supports this.')}", ""]
    return out


def build_markdown(result: AnalysisResult, triage: dict | None = None) -> str:
    findings = result.findings
    lines = ["# Unasked Question Report", ""]
    if c.is_demo(result):
        lines += [f"> **{c.DEMO_NOTICE}**", ""]
    lines += [f"Generated {c.timestamp(result.created_at)}", "", f"*{c.GENERAL_NOTICE}*", ""]

    lines += ["## Summary", ""]
    lines += [_safe(result.overall_summary) if result.overall_summary else "No summary was produced.", ""]
    if result.risk_summary:
        rs = result.risk_summary
        counts = ", ".join(f"{n} {k}" for k, n in rs.counts.items() if n) or "none"
        lines += [f"**Overall risk level: {rs.overall_level.value.capitalize()}** ({counts})", "", _safe(rs.explanation), ""]

    decided = c.triage_counts(triage or {})
    if decided:
        lines += [f"**Your triage so far:** {decided}.", ""]

    if result.warnings:
        lines += ["## Warnings", ""] + [f"- {_safe(c.one_line(w))}" for w in result.warnings] + [""]

    if result.understanding:
        u = result.understanding
        lines += ["## What the engine understood", "", _safe(u.summary), ""]
        lines += [f"- {_safe(c.one_line(x.statement))}" for x in u.facts]
        if u.open_items:
            lines += ["", "Left open by the material itself:", ""] + [f"- {_safe(c.one_line(x))}" for x in u.open_items]
        lines.append("")

    lines += ["## Findings, highest priority first", ""]
    if not findings:
        lines += ["No findings were produced.", ""]
    for i, f in enumerate(findings, 1):
        lines += _finding(i, f, triage)

    lines += ["## Unanswered questions", ""]
    qs = result.unanswered_questions
    lines += [f"{i}. {_safe(c.one_line(q))}" for i, q in enumerate(qs, 1)] if qs else ["None recorded."]
    lines.append("")

    lines += ["## Method", ""]
    if result.risk_summary:
        lines += [_safe(result.risk_summary.formula), ""]
    if result.perspectives:
        lines += ["Perspectives applied: " + "; ".join(_safe(p.name) for p in result.perspectives) + ".", ""]
    lines += ["Models:", ""] + [f"- {_safe(m)}" for m in c.models_line(result)]
    return "\n".join(lines).rstrip() + "\n"
