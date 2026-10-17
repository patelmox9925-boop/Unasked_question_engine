"""Deterministic quality checks applied after the models have spoken.

Models sometimes pad their answer with advice that would fit any project. These checks never invent
or reword anything; they (1) drop unsupported, generic findings, (2) attach the nearest passages of the
material to findings that cite nothing (clearly labelled as search results, not model citations) and
(3) warn when the scores look uncalibrated.
"""

from __future__ import annotations

import re
from collections import Counter

from ..extraction.evidence import resolve_citation
from ..extraction.models import Chunk
from ..extraction.retrieval import EvidenceIndex, tokenize
from ..schemas import EvidenceCitation, Finding, PriorityLevel

GENERIC_PHRASES = (
    "best practice", "industry standard", "industry-standard", "consider implementing", "ensure scalability",
    "ensure security", "regular audits", "stakeholder alignment", "user-friendly", "robust solution",
    "comprehensive plan", "holistic", "going forward", "leverage synerg", "continuous improvement",
    "adequate resources", "proper documentation", "clear communication",
)
MIN_KEPT = 3
RELATED_MIN_OVERLAP = 2
RELATED_MAX = 2
EXCERPT_CHARS = 280


class Material:
    """Token statistics of the project text, used to tell project-specific wording from boilerplate."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        per_chunk = [set(tokenize(c.text)) for c in chunks]
        df: Counter[str] = Counter()
        for tokens in per_chunk:
            df.update(tokens)
        n = max(1, len(chunks))
        self.all_tokens = set(df)
        # In short projects every word is "common"; only apply the document-frequency cut on larger ones.
        self.distinctive = {t for t, c in df.items() if (len(t) >= 4 or t.isdigit()) and (n < 4 or c / n <= 0.5)}

    def anchors(self, text: str) -> int:
        return len({t for t in tokenize(text) if t in self.distinctive})


def is_generic(finding: Finding, material: Material) -> bool:
    if finding.evidence:
        return False
    text = " ".join([finding.title, finding.explanation, finding.critical_question, finding.why_it_matters])
    anchors = material.anchors(text)
    padded = any(phrase in text.lower() for phrase in GENERIC_PHRASES)
    return anchors == 0 or (anchors < 2 and padded)


def drop_generic(findings: list[Finding], chunks: list[Chunk]) -> tuple[list[Finding], int]:
    material = Material(chunks)
    keep = [f for f in findings if not is_generic(f, material)]
    if len(keep) < MIN_KEPT:  # never wipe out a small result; weak findings are better than nothing
        return findings, 0
    return keep, len(findings) - len(keep)


def _best_sentence(chunk: Chunk, query_tokens: set[str]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", chunk.text)
    best = max(sentences, key=lambda s: len(query_tokens & set(tokenize(s))), default=chunk.text)
    best = best.strip() or chunk.text.strip()
    return best if len(best) <= EXCERPT_CHARS else best[:EXCERPT_CHARS].rstrip() + "…"


def attach_related_evidence(findings: list[Finding], chunks: list[Chunk]) -> int:
    """Give citation-less findings the closest passages of the material (marked ``kind="related"``)."""
    if not chunks:
        return 0
    index = EvidenceIndex(chunks)
    by_id = {c.chunk_id: c for c in chunks}
    attached = 0
    for finding in findings:
        if finding.evidence:
            continue
        query = f"{finding.title} {finding.critical_question} {finding.explanation}"
        query_tokens = set(tokenize(query))
        for hit in index.search(query, top_k=RELATED_MAX + 2):
            overlap = query_tokens & set(tokenize(hit.chunk.text))
            if len(overlap) < RELATED_MIN_OVERLAP:
                continue
            evidence = resolve_citation(EvidenceCitation(chunk_id=hit.chunk.chunk_id), by_id)
            if evidence is None:
                continue
            evidence.kind = "related"
            evidence.excerpt = _best_sentence(hit.chunk, query_tokens)
            evidence.quote_verified = False
            finding.evidence.append(evidence)
            attached += 1
            if len(finding.evidence) >= RELATED_MAX:
                break
    return attached


def calibration_warning(findings: list[Finding]) -> str | None:
    if len(findings) < 5:
        return None
    top = sum(1 for f in findings if f.priority_level in (PriorityLevel.CRITICAL, PriorityLevel.HIGH))
    if top / len(findings) >= 0.7:
        return ("Most findings were scored critical or high, which usually means the models were not "
                "discriminating. Trust the order of the list more than the absolute levels.")
    return None
