"""HTTP routes for Phases 1-2: health, config status, project creation (upload), lookup."""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from .. import __version__
from ..config import Settings
from ..errors import ApiError
from ..extraction.models import ExtractedDocument, ExtractionError
from ..extraction.parsers import SUPPORTED_EXTENSIONS, parse_file, parse_text
from ..extraction.untrusted import flag_chunks
from ..schemas import (
    ChunkResponse,
    DocumentSummary,
    HealthResponse,
    ProjectResponse,
    RejectedFile,
)
from ..store import Project, ProjectStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_READ_BLOCK = 1024 * 1024
DESCRIPTION_NAME = "Project description"


def safe_filename(raw: str | None) -> str:
    name = Path((raw or "").replace("\\", "/")).name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:120]


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _store(request: Request) -> ProjectStore:
    return request.app.state.store


async def _save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> None:
    """Stream the upload to disk, aborting as soon as the size limit is exceeded."""
    written = 0
    with destination.open("wb") as handle:
        while chunk := await upload.read(_READ_BLOCK):
            written += len(chunk)
            if written > max_bytes:
                raise ExtractionError(
                    "file_too_large",
                    f"File is larger than the {max_bytes // (1024 * 1024)} MB limit.",
                )
            handle.write(chunk)


def _summary(doc: ExtractedDocument) -> DocumentSummary:
    suspicious = sum(1 for c in doc.chunks if c.flags)
    return DocumentSummary(
        doc_id=doc.doc_id,
        filename=doc.filename,
        doc_type=doc.doc_type,
        char_count=doc.char_count,
        chunk_count=len(doc.chunks),
        warnings=doc.warnings,
        suspicious_chunks=suspicious,
    )


def _project_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        project_id=project.project_id,
        created_at=project.created_at,
        has_description=project.has_description,
        documents=[_summary(d) for d in project.documents],
        rejected=project.rejected,
        total_chunks=len(project.chunks),
    )


def _annotate_injection(doc: ExtractedDocument) -> None:
    flagged = flag_chunks(doc.chunks)
    if flagged:
        doc.warnings.append(
            f"{flagged} section(s) contain text that resembles instructions to an AI. "
            "It is treated strictly as data and will not be followed."
        )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(version=__version__)


@router.get("/config/status")
async def config_status(request: Request) -> dict:
    """Which providers/roles are configured. Never returns key material."""
    from .settings_routes import public

    return public(_settings(request))


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    request: Request,
    description: str = Form(""),
    files: list[UploadFile] | None = File(None),
) -> ProjectResponse:
    settings = _settings(request)
    uploads = [f for f in (files or []) if f.filename]

    if len(uploads) > settings.max_files:
        raise ApiError(400, "too_many_files", f"At most {settings.max_files} files per project.")
    if len(description) > settings.max_description_chars:
        raise ApiError(
            422, "description_too_long",
            f"The description is limited to {settings.max_description_chars} characters.",
        )

    documents: list[ExtractedDocument] = []
    rejected: list[RejectedFile] = []

    if description.strip():
        try:
            desc_doc = parse_text(description, DESCRIPTION_NAME, "desc", markdown=True,
                                  kind="description")
            _annotate_injection(desc_doc)
            documents.append(desc_doc)
        except ExtractionError as exc:  # pragma: no cover - whitespace already excluded
            rejected.append(RejectedFile(filename=DESCRIPTION_NAME, code=exc.code, message=exc.message))

    with tempfile.TemporaryDirectory(prefix="uqe-") as tmp:
        for index, upload in enumerate(uploads):
            name = safe_filename(upload.filename) or f"file-{index + 1}"
            extension = Path(name).suffix.lower()
            if extension not in SUPPORTED_EXTENSIONS:
                rejected.append(RejectedFile(
                    filename=name, code="unsupported_type",
                    message="Unsupported file type. Supported: "
                            + ", ".join(sorted(SUPPORTED_EXTENSIONS)) + ".",
                ))
                continue
            target = Path(tmp) / f"upload-{index}{extension}"
            doc_id = f"d{sum(1 for d in documents if d.doc_id != 'desc') + 1}"
            try:
                await _save_upload(upload, target, settings.max_upload_bytes)
                doc = await run_in_threadpool(
                    parse_file, target, name, doc_id,
                    max_csv_rows=settings.max_csv_rows, max_pdf_pages=settings.max_pdf_pages,
                )
                _annotate_injection(doc)
                documents.append(doc)
            except ExtractionError as exc:
                rejected.append(RejectedFile(filename=name, code=exc.code, message=exc.message))
            except Exception as exc:  # noqa: BLE001
                logger.error("Unexpected extraction failure (%s)", type(exc).__name__)
                rejected.append(RejectedFile(
                    filename=name, code="extraction_failed",
                    message="An unexpected error occurred while reading this file.",
                ))
            finally:
                target.unlink(missing_ok=True)
                await upload.close()

    if not documents:
        raise ApiError(
            422, "empty_input",
            "Provide a project description or at least one readable file.",
            {"rejected": [r.model_dump() for r in rejected]},
        )

    project = _store(request).create(documents, rejected, has_description=bool(description.strip()))
    return _project_response(project)


@router.post("/demo", response_model=ProjectResponse, status_code=201)
async def create_demo_project(request: Request) -> ProjectResponse:
    """Create the sample project with predefined, clearly labelled results. Works with no API keys."""
    from ..demo.data import build_demo_result, load_sample_documents

    documents = load_sample_documents()
    project = _store(request).create(documents, [], has_description=False)
    project.analysis = build_demo_result(project)
    return _project_response(project)


def _get_project(request: Request, project_id: str) -> Project:
    project = _store(request).get(project_id)
    if project is None:
        raise ApiError(404, "project_not_found", "No project with that id.")
    return project


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(request: Request, project_id: str) -> ProjectResponse:
    return _project_response(_get_project(request, project_id))


@router.get("/projects/{project_id}/chunks/{chunk_id}", response_model=ChunkResponse)
async def get_chunk(request: Request, project_id: str, chunk_id: str) -> ChunkResponse:
    chunk = _get_project(request, project_id).chunk_map().get(chunk_id)
    if chunk is None:
        raise ApiError(404, "chunk_not_found", "No evidence chunk with that id.")
    return ChunkResponse(
        chunk_id=chunk.chunk_id, doc_id=chunk.doc_id, text=chunk.text,
        source_label=chunk.source.label(), kind=chunk.kind, flags=chunk.flags,
    )
