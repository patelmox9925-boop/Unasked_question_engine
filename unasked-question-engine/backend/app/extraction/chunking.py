"""Paragraph-aware chunking that keeps source line information."""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CHUNK_CHARS = 1200
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Block:
    text: str
    line_start: int | None = None
    line_end: int | None = None


def paragraph_blocks(lines: list[str], first_line_no: int = 1) -> list[Block]:
    """Group consecutive non-blank lines into blocks, remembering line numbers."""
    blocks: list[Block] = []
    current: list[str] = []
    start = first_line_no
    for offset, raw in enumerate(lines):
        line_no = first_line_no + offset
        if raw.strip():
            if not current:
                start = line_no
            current.append(raw.rstrip())
        elif current:
            blocks.append(Block("\n".join(current), start, line_no - 1))
            current = []
    if current:
        blocks.append(Block("\n".join(current), start, first_line_no + len(lines) - 1))
    return blocks


def hard_split(text: str, max_chars: int) -> list[str]:
    """Split oversize text on sentence boundaries, then by length as a last resort."""
    pieces: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text):
        while len(sentence) > max_chars:
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if sentence.strip():
            pieces.append(sentence)
    merged: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + 1 + len(piece) > max_chars:
            merged.append(current)
            current = piece
        else:
            current = f"{current} {piece}".strip() if current else piece
    if current:
        merged.append(current)
    return merged


def pack_blocks(blocks: list[Block], max_chars: int = MAX_CHUNK_CHARS) -> list[Block]:
    """Merge small blocks together and split oversize ones, up to ``max_chars``."""
    out: list[Block] = []
    current: Block | None = None
    for block in blocks:
        if len(block.text) > max_chars:
            if current:
                out.append(current)
                current = None
            for piece in hard_split(block.text, max_chars):
                out.append(Block(piece, block.line_start, block.line_end))
            continue
        if current and len(current.text) + 2 + len(block.text) <= max_chars:
            current = Block(
                current.text + "\n\n" + block.text, current.line_start, block.line_end
            )
        else:
            if current:
                out.append(current)
            current = block
    if current:
        out.append(current)
    return out
