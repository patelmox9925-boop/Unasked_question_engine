"""Turning raw model findings into trustworthy ``Finding`` objects.

* citations are resolved by the backend (unknown chunk ids dropped, quotes verified)
* the claimed epistemic status is reconciled with the evidence that actually exists
* duplicates are merged and score disagreements are preserved, not averaged away
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Iterable

from ..extraction.evidence import resolve_citation
from ..extraction.models import Chunk
from ..schemas import (
    Category,
    EpistemicStatus,
    Evidence,
    EvidenceCitation,
    Finding,
    RawFinding,
    SynthesizedFinding,
)

ABSENCE_CATEGORIES = {
    Category.MISSING_ASSUMPTION,
    Category.MISSING_INFORMATION,
    Category.MISSING_DEPENDENCY,
    Category.UNASKED_QUESTION,
}
NO_EVIDENCE_NOTE = (
    "No supporting text was found in the provided material for this item; treat it as unverified."
)
ABSENCE_NOTE = (
    "Not directly evidenced: this is based on what the provided material does not say. "
    "It is a potential gap, not a confirmed mistake."
)
DOWNGRADE_NOTE = (
    "The model labelled this a verified fact, but no exact supporting quote could be confirmed in the "
    "source, so it is shown as an inference."
)

_TOKEN = re.compile(r"[a-z0-9]+")
DUPLICATE_THRESHOLD = 0.75
MATCH_THRESHOLD = 0.6


def title_tokens(title: str) -> frozenset[str]:
    return frozenset(_TOKEN.findall(title.lower()))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def match_title(title: str, candidates: Mapping[str, object], threshold: float = MATCH_THRESHOLD) -> str | None:
    """Find the candidate key whose title best matches ``title`` (exact first, then fuzzy)."""
    target = title_tokens(title)
    best_key, best = None, 0.0
    for key in candidates:
        score = jaccard(target, title_tokens(key))
        if score == 1.0:
            return key
        if score > best:
            best_key, best = key, score
    return best_key if best >= threshold else None


def reconcile_status(category: Category, status: EpistemicStatus,
                     evidence: list[Evidence]) -> tuple[EpistemicStatus, str | None]:
    """Never let a finding claim more certainty than its evidence supports."""
    verified = any(e.quote_verified for e in evidence)
    if evidence:
        if status == EpistemicStatus.VERIFIED_FACT and not verified:
            return EpistemicStatus.REASONABLE_INFERENCE, DOWNGRADE_NOTE
        return status, None
    if category in ABSENCE_CATEGORIES:
        if status == EpistemicStatus.VERIFIED_FACT:
            status = EpistemicStatus.REASONABLE_INFERENCE
        return status, ABSENCE_NOTE
    return EpistemicStatus.UNVERIFIED_HYPOTHESIS, NO_EVIDENCE_NOTE


def resolve_evidence(citations: Iterable[EvidenceCitation], chunks: Mapping[str, Chunk]) -> list[Evidence]:
    seen: set[str] = set()
    out: list[Evidence] = []
    for citation in citations:
        if citation.chunk_id in seen:
            continue
        evidence = resolve_citation(citation, chunks)
        if evidence is not None:
            seen.add(citation.chunk_id)
            out.append(evidence)
    return out


def to_finding(raw: RawFinding, chunks: Mapping[str, Chunk], *, raised_by: list[str],
               extra_citations: Iterable[EvidenceCitation] = (), origin: str = "llm") -> Finding:
    evidence = resolve_evidence([*raw.citations, *extra_citations], chunks)
    status, note = reconcile_status(raw.category, raw.epistemic_status, evidence)
    notes = [n for n in (note,) if n]
    disagreement = raw.disagreement_note if isinstance(raw, SynthesizedFinding) else None
    validation = raw.validation_note if isinstance(raw, SynthesizedFinding) else None
    if validation:
        notes.append(validation)
    return Finding(
        id="",
        title=raw.title,
        category=raw.category,
        perspective=raw.perspective,
        explanation=raw.explanation,
        why_it_matters=raw.why_it_matters,
        evidence=evidence,
        evidence_note=" ".join(notes) or None,
        epistemic_status=status,
        impact=raw.impact,
        likelihood=raw.likelihood,
        urgency=raw.urgency,
        recommended_action=raw.recommended_action,
        critical_question=raw.critical_question,
        why_overlooked=raw.why_overlooked,
        raised_by=list(raised_by),
        disagreement_note=disagreement,
        origin=origin,  # type: ignore[arg-type]
    )


def _round_half_up(value: float) -> int:
    return int(value + 0.5)


def _merge_group(group: list[Finding]) -> Finding:
    base = max(group, key=lambda f: (f.impact * f.likelihood, len(f.evidence)))
    if len(group) == 1:
        return base
    merged = base.model_copy(deep=True)
    seen = {e.chunk_id for e in merged.evidence}
    for other in group:
        for ev in other.evidence:
            if ev.chunk_id not in seen:
                merged.evidence.append(ev)
                seen.add(ev.chunk_id)
        for who in other.raised_by:
            if who not in merged.raised_by:
                merged.raised_by.append(who)
    for attr in ("impact", "likelihood", "urgency"):
        setattr(merged, attr, _round_half_up(sum(getattr(f, attr) for f in group) / len(group)))
    spread = {a: max(getattr(f, a) for f in group) - min(getattr(f, a) for f in group)
              for a in ("impact", "likelihood")}
    notes = [f.disagreement_note for f in group if f.disagreement_note]
    if any(v >= 3 for v in spread.values()):
        detail = ", ".join(
            f"{a} {min(getattr(f, a) for f in group)}–{max(getattr(f, a) for f in group)}"
            for a, v in spread.items() if v >= 3
        )
        notes.append(f"Models scored this differently ({detail}); the scores shown are averages.")
    merged.disagreement_note = " ".join(dict.fromkeys(notes)) or None
    status, note = reconcile_status(merged.category, merged.epistemic_status, merged.evidence)
    merged.epistemic_status = status
    if note and (merged.evidence_note is None or note not in merged.evidence_note):
        merged.evidence_note = f"{merged.evidence_note} {note}".strip() if merged.evidence_note else note
    return merged


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    """Merge near-duplicate findings (same category, very similar title)."""
    groups: list[list[Finding]] = []
    for finding in findings:
        tokens = title_tokens(finding.title)
        for group in groups:
            head = group[0]
            if head.category == finding.category and jaccard(tokens, title_tokens(head.title)) >= DUPLICATE_THRESHOLD:
                group.append(finding)
                break
        else:
            groups.append([finding])
    return [_merge_group(g) for g in groups]
