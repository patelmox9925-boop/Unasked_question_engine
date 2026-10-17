"""Routes for Phases 4-6: start/poll analysis, follow-up chat."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..analysis.chat import answer_question
from ..analysis.jobs import JobManager
from ..errors import ApiError
from ..providers.router import LLMRouter
from ..reports.markdown_report import build_markdown
from ..reports.pdf_report import build_pdf
from ..schemas import AnalysisStatus, ChatRequest, ChatResponse, TriageEntry
from .routes import _get_project

router = APIRouter(prefix="/api")


def _jobs(request: Request) -> JobManager:
    return request.app.state.jobs


def _llm(request: Request) -> LLMRouter:
    return request.app.state.router


@router.post("/projects/{project_id}/analyze", response_model=AnalysisStatus, status_code=202)
async def start_analysis(request: Request, project_id: str) -> AnalysisStatus:
    project = _get_project(request, project_id)
    if not _llm(request).role_available("A"):
        raise ApiError(
            409, "no_models_configured",
            "Live analysis needs Model A to be set up. Click Models in the header, add an API key and "
            "choose a model (or set LLM_A_PROVIDER, LLM_A_MODEL and a key in .env). No analysis was run.",
        )
    jobs = _jobs(request)
    if jobs.is_running(project_id):
        raise ApiError(409, "analysis_running", "An analysis is already running for this project.")
    jobs.start(project)
    return jobs.status(project_id, project)


@router.get("/projects/{project_id}/analysis", response_model=AnalysisStatus)
async def get_analysis(request: Request, project_id: str) -> AnalysisStatus:
    project = _get_project(request, project_id)
    return _jobs(request).status(project_id, project)


@router.post("/projects/{project_id}/chat", response_model=ChatResponse)
async def chat(request: Request, project_id: str, body: ChatRequest) -> ChatResponse:
    project = _get_project(request, project_id)
    return await answer_question(_llm(request), project, body.question, body.history)


def _result_for_export(request: Request, project_id: str):
    project = _get_project(request, project_id)
    if project.analysis is None:
        raise ApiError(409, "no_analysis", "There is no analysis to export yet. Run an analysis first.")
    return project.analysis


@router.get("/projects/{project_id}/export.md")
async def export_markdown(request: Request, project_id: str) -> Response:
    result = _result_for_export(request, project_id)
    text = build_markdown(result, _get_project(request, project_id).triage)
    return Response(text, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="unasked-question-report.md"'})


@router.get("/projects/{project_id}/export.pdf")
async def export_pdf(request: Request, project_id: str) -> Response:
    result = _result_for_export(request, project_id)
    data = build_pdf(result, _get_project(request, project_id).triage)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="unasked-question-report.pdf"'})


@router.get("/projects/{project_id}/triage")
async def get_triage(request: Request, project_id: str) -> dict[str, TriageEntry]:
    return _get_project(request, project_id).triage


@router.put("/projects/{project_id}/triage/{finding_id}", response_model=TriageEntry)
async def set_triage(request: Request, project_id: str, finding_id: str, entry: TriageEntry) -> TriageEntry:
    project = _get_project(request, project_id)
    if project.analysis is None or finding_id not in {f.id for f in project.analysis.findings}:
        raise ApiError(404, "finding_not_found", "No finding with that id in this project.")
    if entry.status == "open" and not entry.note:
        project.triage.pop(finding_id, None)
    else:
        project.triage[finding_id] = entry
    return entry
