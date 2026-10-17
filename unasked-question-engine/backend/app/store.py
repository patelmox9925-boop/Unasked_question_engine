"""Small in-memory project store (sufficient for the demo; nothing is persisted to disk)."""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .extraction.models import Chunk, ExtractedDocument
from .schemas import AnalysisResult, RejectedFile, TriageEntry


@dataclass
class Project:
    project_id: str
    created_at: datetime
    has_description: bool
    documents: list[ExtractedDocument]
    rejected: list[RejectedFile] = field(default_factory=list)
    analysis: AnalysisResult | None = None
    triage: dict[str, TriageEntry] = field(default_factory=dict)  # finding id -> decision

    @property
    def chunks(self) -> list[Chunk]:
        return [c for d in self.documents for c in d.chunks]

    def chunk_map(self) -> dict[str, Chunk]:
        return {c.chunk_id: c for c in self.chunks}


class ProjectStore:
    def __init__(self, max_projects: int = 50):
        self._projects: OrderedDict[str, Project] = OrderedDict()
        self._lock = threading.Lock()
        self._max = max_projects

    def create(self, documents: list[ExtractedDocument], rejected: list[RejectedFile],
               has_description: bool) -> Project:
        project = Project(
            project_id=uuid.uuid4().hex[:12],
            created_at=datetime.now(timezone.utc),
            has_description=has_description,
            documents=documents,
            rejected=rejected,
        )
        with self._lock:
            self._projects[project.project_id] = project
            while len(self._projects) > self._max:
                self._projects.popitem(last=False)
        return project

    def get(self, project_id: str) -> Project | None:
        with self._lock:
            return self._projects.get(project_id)
