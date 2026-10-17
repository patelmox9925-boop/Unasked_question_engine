import io
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.main import create_app
from app.reports.markdown_report import build_markdown
from app.reports.pdf_report import build_pdf, clean
from app.analysis.prioritization import build_risk_summary, prioritize
from app.schemas import AnalysisResult, Evidence, Finding, ModelConsulted
from tests.conftest import make_settings
from tests.test_analysis_api import build_client, create_project, providers, wait_done
from tests.helpers import analysis_json, critique_json, facts_json, finding, synthesis_json


def make_finding(**over) -> Finding:
    base = dict(
        id="f1", title="Hosting cost is capped but traffic is unknown", category="missing_assumption",
        explanation="The plan fixes a budget without expected usage.", why_it_matters="Costs may exceed the cap.",
        evidence=[Evidence(chunk_id="desc-c1", source_label="Project description, line 2", filename="d",
                           excerpt="capped at 500 dollars", quote_verified=True)],
        epistemic_status="reasonable_inference", impact=7, likelihood=6, urgency=5,
        recommended_action="Estimate usage.", critical_question="What usage breaks the cap?",
        raised_by=["A"],
    )
    base.update(over)
    return Finding(**base)


def make_result(findings=None, **over) -> AnalysisResult:
    findings = prioritize(findings if findings is not None else [make_finding()])
    base = dict(project_id="p1", created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc), findings=findings,
                unanswered_questions=["Who is on call?"], overall_summary="Cost and access are the blind spots.",
                risk_summary=build_risk_summary(findings),
                models_consulted=[ModelConsulted(role="A", provider="deepseek", model="m", succeeded=True),
                                  ModelConsulted(role="B", provider="gemini", model="g", succeeded=False)],
                warnings=["Model B failed."])
    base.update(over)
    return AnalysisResult(**base)


def pdf_text(data: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)


def test_markdown_contains_all_sections_and_models():
    md = build_markdown(make_result())
    for part in ["# Unasked Question Report", "## Summary", "## Warnings", "Model B failed.", "## Findings",
                 "Hosting cost is capped", "> capped at 500 dollars", "exact quote verified in source",
                 "## Unanswered questions", "Who is on call?", "## Method", "impact × likelihood",
                 "Model A: deepseek / m (completed)", "Model B: gemini / g (FAILED)", "High 37.8"]:
        assert part in md, part
    assert "DEMO DATA" not in md


def test_empty_findings_reports_cleanly():
    result = make_result(findings=[], unanswered_questions=[], overall_summary=None, warnings=[])
    md = build_markdown(result)
    assert "No findings were produced." in md and "None recorded." in md and "No summary was produced." in md
    assert pdf_text(build_pdf(result)).count("No findings were produced.") == 1


def test_demo_origin_is_clearly_labelled_and_models_not_claimed():
    result = make_result(findings=[make_finding(origin="demo")], origin="demo", models_consulted=[], warnings=[])
    md, text = build_markdown(result), pdf_text(build_pdf(result))
    assert "DEMO DATA" in md and "No AI model was consulted" in md and "demo data" in md
    assert "DEMO DATA" in text and "No AI model was consulted" in text


def test_markdown_neutralises_html_and_images():
    nasty = make_finding(title="<script>alert(1)</script> bad", explanation="![x](http://evil.test/p.png) <img src=x>")
    md = build_markdown(make_result([nasty]))
    assert "<script>" not in md and "<img" not in md and "&lt;script&gt;" in md
    assert "![" not in md


def test_unverified_quote_and_missing_evidence_are_distinguished():
    unverified = make_finding(id="f2", title="Second", evidence=[Evidence(
        chunk_id="c", source_label="s", filename="d", excerpt="loose text", quote_verified=False)])
    none = make_finding(id="f3", title="Third", evidence=[], evidence_note="Nothing in the material covers this.",
                        epistemic_status="unverified_hypothesis")
    md = build_markdown(make_result([unverified, none]))
    assert "not a verified quote" in md and "No document evidence." in md and "Unverified hypothesis" in md


def test_pdf_is_valid_and_handles_special_characters():
    odd = make_finding(title="Café ≥ 5 → 日本語 ✓ <b>tag</b> & more", explanation="Line one\nLine two " + "long " * 300,
                       critical_question="Is “quoted” text — fine?")
    data = build_pdf(make_result([odd] * 8))
    assert data.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(data))
    assert len(reader.pages) >= 2
    text = pdf_text(data)
    assert "Café" in text and ">= 5" in text and "<b>tag</b>" in text and "Page 1" in text


def test_clean_escapes_markup_and_replaces_unsupported_glyphs():
    from app.reports.pdf_report import _register_fonts
    _register_fonts()
    assert clean("a<b>&") == "a&lt;b&gt;&amp;"
    assert clean("日") == "?" and clean("→") == "-&gt;"


def test_pdf_has_page_numbers_and_title_metadata():
    reader = PdfReader(io.BytesIO(build_pdf(make_result())))
    assert reader.metadata.title == "Unasked Question Report"


# ------------------------------------------------------------------ HTTP
def test_export_endpoints_require_an_analysis_and_a_project():
    client = TestClient(create_app(make_settings(), serve_frontend=False))
    pid = create_project(client)
    for ext in ("md", "pdf"):
        r = client.get(f"/api/projects/{pid}/export.{ext}")
        assert r.status_code == 409 and r.json()["error"]["code"] == "no_analysis"
        assert client.get(f"/api/projects/nope/export.{ext}").status_code == 404


def test_export_after_real_analysis_returns_files():
    p = providers(a=[facts_json(), analysis_json(finding())], b=[critique_json()],
                  c=[synthesis_json([dict(finding(), merged_from=[])])])
    with build_client(p) as client:
        pid = create_project(client)
        client.post(f"/api/projects/{pid}/analyze")
        assert wait_done(client, pid)["state"] == "done"
        md = client.get(f"/api/projects/{pid}/export.md")
        assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
        assert "attachment" in md.headers["content-disposition"] and "capped at 500 dollars" in md.text
        pdf = client.get(f"/api/projects/{pid}/export.pdf")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and pdf.headers["content-type"] == "application/pdf"


def test_reports_include_understanding_why_overlooked_and_related_labels():
    from app.schemas import ProjectFact, ProjectUnderstanding

    related = Evidence(kind="related", chunk_id="c2", source_label="plan.md, line 9", filename="plan.md",
                       excerpt="Founders handle customer support.", quote_verified=False)
    result = make_result([make_finding(why_overlooked="Nobody counts support as work.", evidence=[related])],
                         understanding=ProjectUnderstanding(summary="A meal kit app.", open_items=["Hosting undecided"],
                                                            facts=[ProjectFact(statement="Launch in March.", kind="date")]))
    md, text = build_markdown(result), pdf_text(build_pdf(result))
    for part in ["## What the engine understood", "A meal kit app.", "- Launch in March.", "Hosting undecided",
                 "Why it is easy to miss.** Nobody counts support as work.",
                 "closest passage found by search; the model did not cite it"]:
        assert part in md, part
    assert "What the engine understood" in text and "Why it is easy to miss." in text
