import io

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.demo.data import SAMPLE_FILES, build_demo_result, load_sample_documents
from app.main import create_app
from app.store import ProjectStore
from tests.conftest import make_settings


def client() -> TestClient:
    return TestClient(create_app(make_settings(), serve_frontend=False))  # no model keys at all


def test_sample_files_exist_and_parse_through_real_extraction():
    docs = load_sample_documents()
    assert [d.filename for d in docs] == list(SAMPLE_FILES)
    assert {d.doc_type for d in docs} == {"markdown", "csv"}


def test_every_demo_quote_is_found_and_verified_in_the_sample():
    project = ProjectStore().create(load_sample_documents(), [], False)
    result = build_demo_result(project)  # raises if any quote is missing from the sample
    assert result.origin == "demo" and result.models_consulted == []
    assert len(result.findings) >= 8
    for f in result.findings:
        assert f.origin == "demo" and f.raised_by == ["demo"] and f.priority_level and f.score_explanation
        assert all(e.quote_verified for e in f.evidence)
    cited = [f for f in result.findings if f.evidence]
    assert len(cited) >= 8
    assert any("potential gap" in (f.evidence_note or "").lower() or "not" in (f.evidence_note or "").lower()
               for f in result.findings if not f.evidence)
    assert [f.id for f in result.findings] == [f"f{i}" for i in range(1, len(result.findings) + 1)]
    scores = [f.priority_score for f in result.findings]
    assert scores == sorted(scores, reverse=True)
    assert result.warnings and "not produced by an AI" in result.warnings[0]


def test_demo_endpoint_works_without_keys_and_is_labelled():
    c = client()
    assert c.get("/api/config/status").json()  # no models configured
    r = c.post("/api/demo")
    assert r.status_code == 201
    pid = r.json()["project_id"]
    assert len(r.json()["documents"]) == 2
    status = c.get(f"/api/projects/{pid}/analysis").json()
    assert status["state"] == "done" and status["result"]["origin"] == "demo"
    assert all(f["origin"] == "demo" for f in status["result"]["findings"])
    # chunks cited as evidence exist in the project
    ev = status["result"]["findings"][0]["evidence"][0]
    assert c.get(f"/api/projects/{pid}/chunks/{ev['chunk_id']}").status_code == 200


def test_demo_cannot_be_chatted_with_but_can_be_exported_with_labels():
    c = client()
    pid = c.post("/api/demo").json()["project_id"]
    assert c.post(f"/api/projects/{pid}/chat", json={"question": "hi", "history": []}).status_code == 409
    md = c.get(f"/api/projects/{pid}/export.md").text
    assert "DEMO DATA" in md and "No AI model was consulted" in md
    reader = PdfReader(io.BytesIO(c.get(f"/api/projects/{pid}/export.pdf").content))
    assert "DEMO DATA" in "\n".join(p.extract_text() for p in reader.pages)


def test_demo_projects_are_independent():
    c = client()
    a, b = (c.post("/api/demo").json()["project_id"] for _ in range(2))
    assert a != b


def test_demo_has_understanding_and_why_overlooked_everywhere():
    project = ProjectStore().create(load_sample_documents(), [], False)
    result = build_demo_result(project)
    assert result.understanding and len(result.understanding.facts) >= 6 and result.understanding.open_items
    assert all(f.evidence and f.evidence[0].quote_verified for f in result.understanding.facts)
    assert all(f.why_overlooked for f in result.findings)


def test_triage_is_stored_validated_and_exported():
    c = client()
    pid = c.post("/api/demo").json()["project_id"]
    assert c.get(f"/api/projects/{pid}/triage").json() == {}
    r = c.put(f"/api/projects/{pid}/triage/f1", json={"status": "accepted", "note": "Ask <b>finance</b> first"})
    assert r.status_code == 200 and c.get(f"/api/projects/{pid}/triage").json()["f1"]["status"] == "accepted"
    c.put(f"/api/projects/{pid}/triage/f2", json={"status": "dismissed", "note": ""})
    md = c.get(f"/api/projects/{pid}/export.md").text
    assert "**Your decision:** Accepted: needs action. Note: Ask &lt;b&gt;finance&lt;/b&gt; first" in md
    assert "**Your triage so far:** 1 accepted, 1 dismissed." in md
    reader = PdfReader(io.BytesIO(c.get(f"/api/projects/{pid}/export.pdf").content))
    assert "Your decision: Accepted" in "\n".join(p.extract_text() for p in reader.pages)
    # reopening without a note clears the decision
    c.put(f"/api/projects/{pid}/triage/f1", json={"status": "open", "note": ""})
    assert "f1" not in c.get(f"/api/projects/{pid}/triage").json()


def test_triage_rejects_unknown_findings_bad_status_and_unanalysed_projects():
    c = client()
    pid = c.post("/api/demo").json()["project_id"]
    assert c.put(f"/api/projects/{pid}/triage/f99", json={"status": "accepted"}).status_code == 404
    assert c.put(f"/api/projects/{pid}/triage/f1", json={"status": "maybe"}).status_code == 422
    assert c.put(f"/api/projects/{pid}/triage/f1", json={"status": "accepted", "note": "x" * 1001}).status_code == 422
    fresh = c.post("/api/projects", data={"description": "Plan: launch in March with two engineers."}).json()["project_id"]
    assert c.put(f"/api/projects/{fresh}/triage/f1", json={"status": "accepted"}).status_code == 404
