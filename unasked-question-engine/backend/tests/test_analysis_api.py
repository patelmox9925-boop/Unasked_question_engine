import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.base import ProviderError, ProviderErrorKind
from app.providers.mock import MockProvider
from tests.conftest import make_settings
from tests.helpers import (
    TEXT,
    analysis_json,
    facts_json,
    chat_json,
    critique_json,
    finding,
    router_for,
    synthesis_json,
)


def build_client(providers, **settings_over):
    router, settings = router_for(providers, **settings_over)
    return TestClient(create_app(settings, llm_router=router, serve_frontend=False))


def providers(a=None, b=None, c=None):
    return {"groq": MockProvider("groq", a or []), "deepseek": MockProvider("deepseek", b or []),
            "gemini": MockProvider("gemini", c or [])}


def create_project(client, description=TEXT):
    r = client.post("/api/projects", data={"description": description})
    assert r.status_code == 201
    return r.json()["project_id"]


def wait_done(client, pid, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/projects/{pid}/analysis").json()
        if body["state"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError("analysis did not finish")


# ------------------------------------------------------------------ analysis
def test_analyze_requires_model_a():
    client = TestClient(create_app(make_settings(), serve_frontend=False))
    pid = create_project(client)
    r = client.post(f"/api/projects/{pid}/analyze")
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_models_configured"
    assert client.get(f"/api/projects/{pid}/analysis").json()["state"] == "idle"


def test_analyze_unknown_project_404():
    client = TestClient(create_app(make_settings(), serve_frontend=False))
    assert client.post("/api/projects/nope/analyze").status_code == 404


def test_full_analysis_flow_over_http():
    p = providers(a=[facts_json(), analysis_json(finding())], b=[critique_json(questions=["Who is on call?"])],
                  c=[synthesis_json([dict(finding(), merged_from=[])])])
    with build_client(p) as client:
        pid = create_project(client)
        started = client.post(f"/api/projects/{pid}/analyze")
        assert started.status_code == 202 and started.json()["state"] == "running"
        assert [s["key"] for s in started.json()["steps"]] == [
            "extract", "context", "facts", "analysis", "critique", "synthesis", "prioritize"]
        body = wait_done(client, pid)
        assert body["state"] == "done" and all(s["status"] == "done" for s in body["steps"])
        result = body["result"]
        assert result["origin"] == "llm" and result["findings"][0]["id"] == "f1"
        assert result["findings"][0]["evidence"][0]["source_label"].startswith("Project description")
        assert result["risk_summary"]["overall_level"] in {"critical", "high", "medium", "low"}
        assert {m["role"] for m in result["models_consulted"]} == {"A", "B", "C"}
        # status endpoint keeps returning the stored result
        assert client.get(f"/api/projects/{pid}/analysis").json()["result"]["findings"]


def test_failed_analysis_reports_error_without_fabricating():
    p = providers(a=[ProviderError("groq", ProviderErrorKind.AUTH, "bad key")])
    with build_client(p) as client:
        pid = create_project(client)
        client.post(f"/api/projects/{pid}/analyze")
        body = wait_done(client, pid)
        assert body["state"] == "failed" and body["result"] is None
        assert "No analysis was produced" in body["error"]
        statuses = {s["key"]: s["status"] for s in body["steps"]}
        assert statuses["facts"] == "failed" and statuses["analysis"] == "skipped" and statuses["synthesis"] == "skipped"


def test_can_rerun_after_failure():
    p = providers(a=[ProviderError("groq", ProviderErrorKind.SERVER, "x"), facts_json(), analysis_json(finding())],
                  b=[critique_json()], c=[synthesis_json([dict(finding(), merged_from=[])])])
    with build_client(p) as client:
        pid = create_project(client)
        client.post(f"/api/projects/{pid}/analyze")
        assert wait_done(client, pid)["state"] == "failed"
        assert client.post(f"/api/projects/{pid}/analyze").status_code == 202
        assert wait_done(client, pid)["state"] == "done"


# ------------------------------------------------------------------ chat
def chat(client, pid, question="What is the budget?", history=None):
    return client.post(f"/api/projects/{pid}/chat", json={"question": question, "history": history or []})


def test_chat_without_models_is_a_clear_409():
    client = TestClient(create_app(make_settings(), serve_frontend=False))
    pid = create_project(client)
    r = chat(client, pid)
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_models_configured"


def test_chat_grounded_answer_with_verified_evidence_and_known_findings_only():
    reply = chat_json("The budget is capped at **500 dollars** per month.",
                      citations=[{"chunk_id": "desc-c1", "quote": "capped at 500 dollars"},
                                 {"chunk_id": "nope-c9", "quote": "invented"}],
                      finding_ids=["f1", "f99"])
    p = providers(c=[reply], a=[facts_json(), analysis_json(finding())], b=[critique_json()])
    p["gemini"].script.appendleft(synthesis_json([dict(finding(), merged_from=[])]))
    with build_client(p) as client:
        pid = create_project(client)
        client.post(f"/api/projects/{pid}/analyze")
        wait_done(client, pid)
        r = chat(client, pid, "What is the budget?", [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}])
        body = r.json()
        assert r.status_code == 200 and body["grounding"] == "grounded"
        assert [e["chunk_id"] for e in body["evidence"]] == ["desc-c1"] and body["evidence"][0]["quote_verified"]
        assert body["finding_ids"] == ["f1"]  # f99 unknown, dropped
        assert body["model"]["role"] == "C" and body["model"]["succeeded"] is True
        prompt = p["gemini"].calls[-1][0]
        assert "capped at 500 dollars" in prompt.user  # retrieved passage
        assert "USER: hi" in prompt.user and "QUESTION: What is the budget?" in prompt.user
        assert "Hosting cost is capped" in prompt.user  # analysis findings included
        assert "UNTRUSTED" in prompt.system


def test_chat_downgrades_grounding_when_citations_cannot_be_verified():
    p = providers(a=[chat_json("Probably.", citations=[{"chunk_id": "zzz", "quote": "x"}], grounding="grounded")])
    with build_client(p, llm_b_provider="", llm_b_model="", llm_c_provider="", llm_c_model="") as client:
        pid = create_project(client)
        body = chat(client, pid).json()
        assert body["grounding"] == "partly_grounded" and body["evidence"] == []
        assert any("could be verified" in w or "verified" in w for w in body["warnings"])
        assert any("No analysis has been run" in w for w in body["warnings"])


def test_chat_not_in_material_passes_through():
    p = providers(a=[chat_json("The material does not say.", grounding="not_in_material")])
    with build_client(p, llm_b_provider="", llm_b_model="", llm_c_provider="", llm_c_model="") as client:
        pid = create_project(client)
        body = chat(client, pid, "What is the CEO's favourite colour?").json()
        assert body["grounding"] == "not_in_material"
        # a small project is always sent whole, even when the question shares no keywords with it
        assert "capped at 500 dollars" in p["groq"].calls[0][0].user


def test_large_projects_use_retrieval_then_fall_back_to_opening_sections():
    from app.analysis.chat import build_chat_request
    from tests.helpers import project_from

    filler = "\n\n".join(f"Paragraph {i} about routine matters. " + "lorem ipsum dolor " * 40 for i in range(60))
    project = project_from("# Opening\nThe project goal is a meal kit app.\n\n" + filler +
                           "\n\n# Security\nThe zebra protocol handles encryption keys.\n")
    targeted = build_chat_request(project, "How does the zebra protocol work?", []).user
    assert "zebra protocol" in targeted and "Paragraph 30" not in targeted
    assert targeted.count("chunk_id=") <= 6
    blind = build_chat_request(project, "What assumptions matter most?", []).user  # no keyword overlap
    assert "meal kit app" in blind and "Paragraph 59" not in blind


def test_chat_input_validation_and_provider_failure():
    p = providers(a=[ProviderError("groq", ProviderErrorKind.TIMEOUT, "slow")])
    with build_client(p, llm_b_provider="", llm_b_model="", llm_c_provider="", llm_c_model="") as client:
        pid = create_project(client)
        assert chat(client, pid, "   ").status_code == 422
        assert chat(client, pid, "x" * 2001).status_code == 422
        assert client.post(f"/api/projects/{pid}/chat", json={"question": "q", "history": [{"role": "system", "content": "x"}]}).status_code == 422
        r = chat(client, pid)
        assert r.status_code == 502 and r.json()["error"]["code"] == "llm_unavailable"
        assert chat(client, "nope").status_code == 404


def test_chat_prefers_role_c_then_a():
    p = providers(a=[chat_json("from A")], c=[chat_json("from C")])
    with build_client(p, llm_b_provider="", llm_b_model="") as client:
        pid = create_project(client)
        assert chat(client, pid).json()["answer"] == "from C"
