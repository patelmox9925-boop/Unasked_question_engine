from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_settings(**overrides) -> Settings:
    """Settings that ignore any real .env file and real environment keys."""
    base = dict(
        deepseek_api_key=None,
        groq_api_key=None,
        gemini_api_key=None,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))


def make_pdf(pages: list[str]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    for text in pages:
        y = 740
        for line in text.splitlines():
            pdf.drawString(72, y, line)
            y -= 16
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_docx(build) -> bytes:
    from docx import Document

    document = Document()
    build(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
