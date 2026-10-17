import os
import stat

import httpx
import pytest
from fastapi.testclient import TestClient

from app import envfile
from app.api import settings_routes
from app.main import create_app
from app.providers.groq_provider import GroqProvider
from tests.conftest import make_settings

KEY = "gsk_test_key_0123456789abcdef"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", dict(os.environ))  # keep test edits out of the real environment
    for name in list(os.environ):
        if name.startswith(("LLM_", "GEMINI_", "GROQ_", "DEEPSEEK_")):
            os.environ.pop(name)
    return tmp_path / ".env"


def make_client(env, **kw):
    app = create_app(make_settings(), serve_frontend=False)
    app.state.env_file = env
    return TestClient(app, **kw)


# ------------------------------------------------------------------ env file writer
def test_env_file_update_preserves_comments_and_order(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", dict(os.environ))
    path = tmp_path / ".env"
    path.write_text("# my notes\nLOG_LEVEL=INFO\nGROQ_API_KEY=old-key-value\n\nOTHER=1\n")
    envfile.update_env_file(path, {"GROQ_API_KEY": "new-key-value", "LLM_A_MODEL": "m1"})
    text = path.read_text()
    assert text.splitlines()[:3] == ["# my notes", "LOG_LEVEL=INFO", "GROQ_API_KEY=new-key-value"]
    assert "OTHER=1" in text and text.rstrip().endswith("LLM_A_MODEL=m1")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert os.environ["GROQ_API_KEY"] == "new-key-value"
    envfile.update_env_file(path, {"GROQ_API_KEY": ""})
    assert "GROQ_API_KEY=\n" in path.read_text() and "GROQ_API_KEY" not in os.environ


@pytest.mark.parametrize("bad", ["has space", 'quo"te', "line\nbreak", "a=b c", "x" * 401, "semi;colon"])
def test_env_file_rejects_unsafe_values(tmp_path, monkeypatch, bad):
    monkeypatch.setattr(os, "environ", dict(os.environ))
    with pytest.raises(envfile.EnvValueError):
        envfile.update_env_file(tmp_path / ".env", {"LLM_A_MODEL": bad})
    assert not (tmp_path / ".env").exists()


def test_env_file_rejects_bad_names(tmp_path):
    with pytest.raises(envfile.EnvValueError):
        envfile.update_env_file(tmp_path / ".env", {"lower": "x"})


# ------------------------------------------------------------------ API
def test_saving_settings_updates_status_without_restart_and_never_returns_the_key(env):
    c = make_client(env)
    assert c.get("/api/config/status").json()["live_analysis_available"] is False
    r = c.put("/api/settings", json={
        "keys": {"groq": KEY},
        "roles": {"A": {"provider": "groq", "model": "llama-x"}, "B": {}, "C": {}},
    })
    assert r.status_code == 200 and KEY not in r.text
    body = r.json()
    assert body["roles"]["A"]["primary_ready"] and body["live_analysis_available"]
    assert body["providers"]["groq"] == {**body["providers"]["groq"], "api_key_configured": True, "key_hint": "••••cdef"}
    assert KEY not in c.get("/api/config/status").text and KEY not in c.get("/api/settings").text
    saved = env.read_text()
    assert f"GROQ_API_KEY={KEY}" in saved and "LLM_A_PROVIDER=groq" in saved
    # the router already uses the new settings
    assert c.app.state.router.role_available("A")


def test_omitted_key_is_kept_and_empty_key_removes_it(env):
    c = make_client(env)
    c.put("/api/settings", json={"keys": {"groq": KEY}})
    c.put("/api/settings", json={"roles": {"A": {"provider": "groq", "model": "m"}}})  # key not mentioned
    assert c.get("/api/settings").json()["providers"]["groq"]["api_key_configured"] is True
    c.put("/api/settings", json={"keys": {"groq": ""}})
    assert c.get("/api/settings").json()["providers"]["groq"]["api_key_configured"] is False


@pytest.mark.parametrize("payload", [
    {"keys": {"groq": "has a space"}},
    {"keys": {"skynet": "abcdefghijkl"}},
    {"roles": {"Z": {"provider": "groq", "model": "m"}}},
    {"roles": {"A": {"provider": "openai", "model": "m"}}},
    {"roles": {"A": {"provider": "groq", "model": "bad model\nLLM_B_MODEL=x"}}},
])
def test_invalid_settings_are_rejected_and_nothing_is_written(env, payload):
    c = make_client(env)
    r = c.put("/api/settings", json=payload)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_setting"
    assert not env.exists()


def test_settings_are_local_only(env):
    remote = make_client(env, client=("203.0.113.9", 5555))
    for call in (lambda: remote.get("/api/settings"), lambda: remote.put("/api/settings", json={}),
                 lambda: remote.post("/api/settings/test", json={"provider": "groq"})):
        r = call()
        assert r.status_code == 403 and r.json()["error"]["code"] == "settings_local_only"


def test_write_failure_is_reported_cleanly(tmp_path):
    c = make_client(tmp_path / "missing_dir" / "deeper" / ".env")
    (tmp_path / "missing_dir").write_text("a file, not a folder")
    r = c.put("/api/settings", json={"keys": {"groq": KEY}})
    assert r.status_code == 500 and r.json()["error"]["code"] == "settings_not_saved" and KEY not in r.text


# ------------------------------------------------------------------ connection test
def patch_provider(monkeypatch, handler, seen=None):
    def fake_build(name, settings, client=None):
        cls = settings_routes.build_provider.__wrapped__ if False else GroqProvider
        return cls(api_key=settings.api_key_for(name), base_url="https://api.test/v1", max_retries=0,
                   client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(settings_routes, "build_provider", fake_build)


def test_connection_test_lists_models_and_checks_the_model(env, monkeypatch):
    def handler(request):
        if request.method == "GET":
            assert request.headers["authorization"] == f"Bearer {KEY}"
            return httpx.Response(200, json={"data": [{"id": "good-model"}, {"id": "other"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    patch_provider(monkeypatch, handler)
    c = make_client(env)
    r = c.post("/api/settings/test", json={"provider": "groq", "api_key": KEY})
    assert r.json()["ok"] and r.json()["models"] == ["good-model", "other"] and KEY not in r.text
    r = c.post("/api/settings/test", json={"provider": "groq", "api_key": KEY, "model": "good-model"})
    assert r.json()["ok"] and "both work" in r.json()["message"]
    r = c.post("/api/settings/test", json={"provider": "groq", "api_key": KEY, "model": "typo-model"})
    assert not r.json()["ok"] and r.json()["stage"] == "model" and "not in this account" in r.json()["message"]
    assert not env.exists()  # testing never saves anything


def test_connection_test_reports_bad_keys_without_echoing_them(env, monkeypatch):
    patch_provider(monkeypatch, lambda r: httpx.Response(401, text=f"bad key {KEY}"))
    c = make_client(env)
    r = c.post("/api/settings/test", json={"provider": "groq", "api_key": KEY})
    body = r.json()
    assert r.status_code == 200 and not body["ok"] and body["stage"] == "key" and KEY not in r.text
    assert "rejected the credentials" in body["message"]


def test_connection_test_without_any_key_and_with_saved_key(env, monkeypatch):
    patch_provider(monkeypatch, lambda r: httpx.Response(200, json={"data": [{"id": "m"}]}))
    c = make_client(env)
    assert not c.post("/api/settings/test", json={"provider": "groq"}).json()["ok"]
    c.put("/api/settings", json={"keys": {"groq": KEY}})
    assert c.post("/api/settings/test", json={"provider": "groq"}).json()["ok"]  # uses the saved key
    assert c.post("/api/settings/test", json={"provider": "nope"}).status_code == 422
    assert c.post("/api/settings/test", json={"provider": "groq", "api_key": "bad key!"}).status_code == 422
