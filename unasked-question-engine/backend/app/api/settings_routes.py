"""Settings page API: choose providers/models per role, store keys, test connections.

Security model: this app is a local, single-user tool. These routes can store API keys and spend them,
so they only answer requests from the local machine (override with ALLOW_REMOTE_SETTINGS=true if you
put the app behind your own authentication). Keys are write-only: they are never returned.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, SecretStr

from .. import envfile
from ..config import (
    ENV_FILE,
    PROVIDER_INFO,
    ROLES,
    SUPPORTED_PROVIDERS,
    Settings,
)
from ..errors import ApiError
from ..providers import build_provider
from ..providers.base import LLMRequest, ProviderError
from ..security import redact

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings")

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _require_local(request: Request) -> None:
    settings: Settings = request.app.state.settings
    host = request.client.host if request.client else ""
    if settings.allow_remote_settings or host in LOCAL_HOSTS:
        return
    raise ApiError(403, "settings_local_only",
                   "Settings can only be changed from the computer the app is running on.")


class RoleUpdate(BaseModel):
    provider: str = ""
    model: str = ""
    fallback_provider: str = ""
    fallback_model: str = ""


class SettingsUpdate(BaseModel):
    roles: dict[str, RoleUpdate] = Field(default_factory=dict)
    # provider -> new key. Omitted/null = keep; "" = remove.
    keys: dict[str, str | None] = Field(default_factory=dict)


class TestRequest(BaseModel):
    provider: str
    model: str = ""
    api_key: str | None = None  # test a key before saving it; otherwise the saved key is used


def _key_hint(settings: Settings, provider: str) -> str | None:
    key = settings.api_key_for(provider)
    return f"••••{key[-4:]}" if key and len(key) >= 12 else ("••••" if key else None)


def public(settings: Settings) -> dict:
    status = settings.public_status()
    for name, info in status["providers"].items():
        info["key_hint"] = _key_hint(settings, name)
    return status


def _apply(request: Request, updates: dict[str, str | None]) -> Settings:
    env_path = getattr(request.app.state, "env_file", ENV_FILE)  # tests point this at a temp file
    try:
        envfile.update_env_file(env_path, updates)
    except envfile.EnvValueError as exc:
        raise ApiError(422, "invalid_setting", str(exc)) from exc
    except OSError as exc:
        logger.error("Could not write settings file (%s)", type(exc).__name__)
        raise ApiError(500, "settings_not_saved", "The settings file could not be written. "
                       "Check that the project folder is writable.") from exc
    new = Settings(_env_file=str(env_path))
    request.app.state.settings = new
    request.app.state.router.reconfigure(new)
    return new


@router.get("")
async def get_settings_view(request: Request) -> dict:
    _require_local(request)
    return public(request.app.state.settings)


@router.put("")
async def save_settings(request: Request, body: SettingsUpdate) -> dict:
    _require_local(request)
    updates: dict[str, str | None] = {}
    for provider, key in body.keys.items():
        if provider not in SUPPORTED_PROVIDERS:
            raise ApiError(422, "invalid_setting", f"Unknown provider '{provider}'.")
        if key is None:
            continue
        updates[PROVIDER_INFO[provider]["key_env"]] = key.strip()
    for role, cfg in body.roles.items():
        if role not in ROLES:
            raise ApiError(422, "invalid_setting", f"Unknown role '{role}'.")
        for field in ("provider", "fallback_provider"):
            value = getattr(cfg, field).strip().lower()
            if value and value not in SUPPORTED_PROVIDERS:
                raise ApiError(422, "invalid_setting", f"Unknown provider '{value}'.")
            updates[f"LLM_{role}_{field.upper()}"] = value
        updates[f"LLM_{role}_MODEL"] = cfg.model.strip()
        updates[f"LLM_{role}_FALLBACK_MODEL"] = cfg.fallback_model.strip()
    if not updates:
        return public(request.app.state.settings)
    return public(_apply(request, updates))


@router.post("/test")
async def test_connection(request: Request, body: TestRequest) -> dict:
    """Check a key (and optionally a model) with a tiny request. Never echoes the key."""
    _require_local(request)
    if body.provider not in SUPPORTED_PROVIDERS:
        raise ApiError(422, "invalid_setting", f"Unknown provider '{body.provider}'.")
    settings: Settings = request.app.state.settings
    typed = (body.api_key or "").strip()
    if typed:
        try:
            envfile.validate_value("API key", typed)
        except envfile.EnvValueError as exc:
            raise ApiError(422, "invalid_setting", str(exc)) from exc
        settings = settings.model_copy(update={f"{body.provider}_api_key": SecretStr(typed)})
    if not settings.api_key_for(body.provider):
        return {"ok": False, "stage": "key", "message": "No API key yet. Paste one first.", "models": []}

    secrets = [*settings.secret_values()]
    provider = build_provider(body.provider, settings)
    try:
        models = await provider.list_models()
    except ProviderError as exc:
        return {"ok": False, "stage": "key", "message": redact(str(exc), secrets), "models": []}

    result = {"ok": True, "stage": "key", "models": models[:300],
              "message": f"Key works. {len(models)} model(s) available."}
    model = body.model.strip()
    if model:
        if models and model not in models:
            result.update(ok=False, stage="model",
                          message=f"The key works, but '{model}' is not in this account's model list. "
                                  "Pick one from the list.")
            return result
        try:
            await provider.generate(LLMRequest(system="Reply with the JSON object {\"ok\": true}.",
                                               user="ping", max_tokens=20, temperature=0), model)
        except ProviderError as exc:
            result.update(ok=False, stage="model", message=redact(str(exc), secrets))
            return result
        result["message"] = f"Key and model '{model}' both work."
    return result
