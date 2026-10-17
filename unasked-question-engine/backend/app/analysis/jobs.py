"""Background analysis jobs so the UI can show live progress."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from ..providers.router import LLMRouter
from ..schemas import AnalysisResult, AnalysisStatus, AnalysisStep, StepStatus
from ..security import redact
from ..store import Project
from .pipeline import STEP_LABELS, AnalysisFailed, AnalysisPipeline

logger = logging.getLogger(__name__)


@dataclass
class AnalysisJob:
    project_id: str
    state: str = "running"
    steps: list[AnalysisStep] = field(default_factory=list)
    result: AnalysisResult | None = None
    error: str | None = None
    task: asyncio.Task | None = None


class JobManager:
    def __init__(self, router: LLMRouter, secrets_provider=lambda: []):
        self.pipeline = AnalysisPipeline(router)
        self._jobs: dict[str, AnalysisJob] = {}
        self._tasks: set[asyncio.Task] = set()
        self._secrets = secrets_provider

    def is_running(self, project_id: str) -> bool:
        job = self._jobs.get(project_id)
        return bool(job and job.state == "running")

    def start(self, project: Project) -> AnalysisJob:
        job = AnalysisJob(
            project_id=project.project_id,
            steps=[AnalysisStep(key=k, label=label) for k, label in STEP_LABELS],
        )
        self._jobs[project.project_id] = job
        job.task = asyncio.create_task(self._run(job, project))
        self._tasks.add(job.task)
        job.task.add_done_callback(self._tasks.discard)
        return job

    async def _run(self, job: AnalysisJob, project: Project) -> None:
        def progress(key: str, status: StepStatus, detail: str | None) -> None:
            for step in job.steps:
                if step.key == key:
                    step.status, step.detail = status, detail

        try:
            result = await self.pipeline.run(project, progress)
            project.analysis = result
            job.result, job.state = result, "done"
        except AnalysisFailed as exc:
            job.state, job.error = "failed", exc.message
        except Exception as exc:  # noqa: BLE001
            logger.exception("Analysis crashed (%s)", type(exc).__name__)
            job.state = "failed"
            job.error = redact("An unexpected error occurred during analysis. See server logs.",
                               self._secrets())
        finally:
            if job.state == "failed":
                for step in job.steps:
                    if step.status in ("pending", "running"):
                        step.status = "skipped" if step.status == "pending" else "failed"
                        step.detail = step.detail or "Not run because analysis stopped."

    def status(self, project_id: str, project: Project | None = None) -> AnalysisStatus:
        job = self._jobs.get(project_id)
        if job is None:
            existing = project.analysis if project else None
            return AnalysisStatus(project_id=project_id, state="done" if existing else "idle",
                                  result=existing)
        return AnalysisStatus(project_id=project_id, state=job.state,  # type: ignore[arg-type]
                              steps=job.steps, result=job.result, error=job.error)
