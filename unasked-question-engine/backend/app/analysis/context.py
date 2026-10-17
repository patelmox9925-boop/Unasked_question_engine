"""Choose which evidence chunks go to the models (size-bounded, relevance-ranked)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..extraction.models import Chunk
from ..extraction.retrieval import EvidenceIndex
from .perspectives import Perspective

CONTEXT_BUDGET_CHARS = 60000


@dataclass
class AnalysisContext:
    chunks: list[Chunk]  # chunks actually sent, in document order
    total_chunks: int
    truncated: bool
    perspectives: list[Perspective]
    warnings: list[str] = field(default_factory=list)


def _always_keep(chunk: Chunk) -> bool:
    return chunk.kind in ("description", "dataset_profile")


def build_context(all_chunks: list[Chunk], perspectives: list[Perspective],
                  budget: int = CONTEXT_BUDGET_CHARS) -> AnalysisContext:
    total = sum(len(c.text) for c in all_chunks)
    if total <= budget:
        return AnalysisContext(list(all_chunks), len(all_chunks), False, perspectives)

    index = EvidenceIndex(all_chunks)
    relevance: dict[str, float] = {}
    for p in perspectives:
        for hit in index.search(f"{p.name} {p.focus}", top_k=len(all_chunks)):
            relevance[hit.chunk.chunk_id] = relevance.get(hit.chunk.chunk_id, 0.0) + hit.score

    order = {c.chunk_id: i for i, c in enumerate(all_chunks)}
    ranked = sorted(all_chunks, key=lambda c: (not _always_keep(c), -relevance.get(c.chunk_id, 0.0),
                                               order[c.chunk_id]))
    chosen: list[Chunk] = []
    used = 0
    for chunk in ranked:
        if used + len(chunk.text) > budget:
            continue
        chosen.append(chunk)
        used += len(chunk.text)
    chosen.sort(key=lambda c: order[c.chunk_id])
    warning = (
        f"The material is large: {len(chosen)} of {len(all_chunks)} sections (the most relevant ones) "
        "were sent to the models, so some findings may miss content from the omitted sections."
    )
    return AnalysisContext(chosen, len(all_chunks), True, perspectives, [warning])
