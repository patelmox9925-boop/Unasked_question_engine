"""Dependency-free BM25 retrieval over chunks, plus quote verification."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from .models import Chunk

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have if in into is it its of on or "
    "our that the their then there these they this to was we were will with you your".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    score: float


class EvidenceIndex:
    """BM25 index so only relevant evidence is sent to models and shown per finding."""

    def __init__(self, chunks: Iterable[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = list(chunks)
        self.k1, self.b = k1, b
        self._tokens = [tokenize(c.text) for c in self.chunks]
        self._tf = [Counter(t) for t in self._tokens]
        self._avg_len = (
            sum(len(t) for t in self._tokens) / len(self._tokens) if self._tokens else 0.0
        )
        self._df: Counter[str] = Counter()
        for tf in self._tf:
            self._df.update(tf.keys())

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        terms = tokenize(query)
        if not terms or not self.chunks:
            return []
        n = len(self.chunks)
        hits: list[SearchHit] = []
        for index, chunk in enumerate(self.chunks):
            tf, length = self._tf[index], len(self._tokens[index])
            score = 0.0
            for term in set(terms):
                freq = tf.get(term, 0)
                if not freq:
                    continue
                df = self._df[term]
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                norm = freq + self.k1 * (1 - self.b + self.b * length / (self._avg_len or 1))
                score += idf * freq * (self.k1 + 1) / norm
            if score > 0:
                hits.append(SearchHit(chunk, score))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]


_QUOTE_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTE_CHARS)).strip().casefold()


def verify_excerpt(excerpt: str, chunk_text: str) -> bool:
    """True only if every ``...``-separated segment of ``excerpt`` appears in the chunk."""
    haystack = _normalise(chunk_text)
    segments = [
        _normalise(s).strip(" \"'") for s in re.split(r"\.\.\.|…", excerpt) if s.strip()
    ]
    segments = [s for s in segments if s]
    return bool(segments) and all(s in haystack for s in segments)
