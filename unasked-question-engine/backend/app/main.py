"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__
from .analysis.jobs import JobManager
from .api.analysis_routes import router as analysis_router
from .api.routes import router
from .api.settings_routes import router as settings_router
from .config import Settings, get_settings
from .errors import install_error_handlers
from .logging_setup import setup_logging
from .providers.router import LLMRouter
from .store import ProjectStore

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app(settings: Settings | None = None, llm_router: LLMRouter | None = None,
               serve_frontend: bool = True) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(title="The Unasked Question Engine", version=__version__)
    app.state.settings = settings
    current_secrets = lambda: app.state.settings.secret_values()  # noqa: E731 - follows live settings edits
    setup_logging(settings.log_level, current_secrets)
    app.state.store = ProjectStore()
    app.state.router = llm_router or LLMRouter(settings)
    app.state.jobs = JobManager(app.state.router, current_secrets)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        # any local port (dev servers, preview servers); remote sites are still blocked
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(analysis_router)
    app.include_router(settings_router)

    # Serve the built frontend (if present) so one command runs everything.
    if serve_frontend and FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    return app


app = create_app()
