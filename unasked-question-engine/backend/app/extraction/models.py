"""Data structures for extracted documents and evidence chunks."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ExtractionError(Exception):
    """Raised when a file cannot be turned into usable text. Message is user-safe."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class SourceRef(BaseModel):
    filename: str
    page: int | None = None
    heading: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    line_start: int | None = None
    line_end: int | None = None

    def label(self) -> str:
        parts = [self.filename]
        if self.page is not None:
            parts.append(f"page {self.page}")
        if self.heading:
            parts.append(f'section "{self.heading}"')
        if self.row_start is not None:
            if self.row_end in (None, self.row_start):
                parts.append(f"row {self.row_start}")
            else:
                parts.append(f"rows {self.row_start}–{self.row_end}")
        if self.line_start is not None:
            if self.line_end in (None, self.line_start):
                parts.append(f"line {self.line_start}")
            else:
                parts.append(f"lines {self.line_start}–{self.line_end}")
        return ", ".join(parts)


ChunkKind = Literal["text", "dataset_profile", "dataset_rows", "description"]


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    source: SourceRef
    kind: ChunkKind = "text"
    flags: list[str] = Field(default_factory=list)


class ExtractedDocument(BaseModel):
    doc_id: str
    filename: str
    doc_type: str
    char_count: int
    chunks: list[Chunk]
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
