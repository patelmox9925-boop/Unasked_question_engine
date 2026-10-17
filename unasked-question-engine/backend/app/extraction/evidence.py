"""Turn a model's chunk citation into real, verifiable ``Evidence``.

Models may only name a ``chunk_id`` (and optionally quote from it). The source
location always comes from our own chunk records, and a quote is shown as a
quote only if it really appears in that chunk. Otherwise the excerpt is the
start of the chunk itself, flagged ``quote_verified=False``. Unknown chunk ids
are dropped, so evidence can never be invented.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..schemas import Evidence, EvidenceCitation
from .models import Chunk
from .retrieval import verify_excerpt

EXCERPT_FALLBACK_CHARS = 300


def resolve_citation(citation: EvidenceCitation, chunks: Mapping[str, Chunk]) -> Evidence | None:
    chunk = chunks.get(citation.chunk_id)
    if chunk is None:
        return None
    verified = bool(citation.quote) and verify_excerpt(citation.quote or "", chunk.text)
    if verified:
        excerpt = (citation.quote or "").strip()
    else:
        excerpt = chunk.text[:EXCERPT_FALLBACK_CHARS].strip()
        if len(chunk.text) > EXCERPT_FALLBACK_CHARS:
            excerpt += "…"
    src = chunk.source
    return Evidence(
        chunk_id=chunk.chunk_id,
        source_label=src.label(),
        filename=src.filename,
        page=src.page,
        heading=src.heading,
        row_start=src.row_start,
        row_end=src.row_end,
        line_start=src.line_start,
        line_end=src.line_end,
        excerpt=excerpt,
        quote_verified=verified,
    )
