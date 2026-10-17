"""Application settings, loaded from environment variables / .env.

API keys are held as ``SecretStr`` and are never included in ``public_status``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"  # written by the Settings page
ROLES = ("A", "B", "C")
SUPPORTED_PROVIDERS = ("gemini", "groq", "deepseek")
DEFAULT_CONTEXT_CHARS = 60000

# Static facts about each provider, shown in the Settings panel and used for sizing requests.
# "context_chars" is how much project material one request may carry (conservative: free tiers of
# some providers reject large requests). Override with <PROVIDER>_CONTEXT_CHARS.
PROVIDER_INFO: dict[str, dict[str, Any]] = {
    "gemini": {
        "label": "Google Gemini", "key_env": "GEMINI_API_KEY", "context_chars": 60000,
        "key_url": "https://aistudio.google.com/apikey",
        "strengths": "Very large context window; good for reading the whole project.",
        "default_role": "A", "suggested_models": ["gemini-2.5-flash", "gemini-2.5-pro"],
    },
    "groq": {
        "label": "Groq", "key_env": "GROQ_API_KEY", "context_chars": 24000,
        "key_url": "https://console.groq.com/keys",
        "strengths": "Very fast; good for the independent critique. Free tiers limit request size.",
        "default_role": "B", "suggested_models": ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"],
    },
    "deepseek": {
        "label": "DeepSeek", "key_env": "DEEPSEEK_API_KEY", "context_chars": 60000,
        "key_url": "https://platform.deepseek.com/api_keys",
        "strengths": "Strong reasoning at low cost; good for validation and synthesis.",
        "default_role": "C", "suggested_models": ["deepseek-chat"],
    },
}
ROLE_TASKS = {
    "A": "Initial analysis and finding extraction",
    "B": "Independent critique, missing-question discovery, counterarguments",
    "C": "Evidence validation, deduplication, prioritization, final synthesis",
}


class RoleConfig(BaseModel):
    role: str
    provider: str = ""
    model: str = ""
    fallback_provider: str = ""
    fallback_model: str = ""

    @property
    def has_primary(self) -> bool:
        return bool(self.provider and self.model)

    @property
    def has_fallback(self) -> bool:
        return bool(self.fallback_provider and self.fallback_model)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / "backend" / ".env"), str(ENV_FILE)), env_file_encoding="utf-8", extra="ignore"
    )

    # General
    app_env: str = "development"
    log_level: str = "INFO"
    allow_remote_settings: bool = False  # Settings page is localhost-only unless enabled
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Upload limits
    max_upload_mb: int = 10
    max_files: int = 10
    max_description_chars: int = 20000
    max_csv_rows: int = 20000
    max_pdf_pages: int = 300

    # LLM call behaviour
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2
    llm_backoff_base_seconds: float = 1.0
    llm_max_retry_delay_seconds: float = 30.0
    llm_max_schema_repairs: int = 1

    # Provider credentials and endpoints
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    deepseek_base_url: str = "https://api.deepseek.com"
    # Max characters of project material per request, per provider (0 = built-in default).
    gemini_context_chars: int = 0
    groq_context_chars: int = 0
    deepseek_context_chars: int = 0

    # Role routing (provider + model per task, with optional fallback)
    llm_a_provider: str = ""
    llm_a_model: str = ""
    llm_a_fallback_provider: str = ""
    llm_a_fallback_model: str = ""
    llm_b_provider: str = ""
    llm_b_model: str = ""
    llm_b_fallback_provider: str = ""
    llm_b_fallback_model: str = ""
    llm_c_provider: str = ""
    llm_c_model: str = ""
    llm_c_fallback_provider: str = ""
    llm_c_fallback_model: str = ""

    @field_validator(
        "llm_a_provider",
        "llm_a_fallback_provider",
        "llm_b_provider",
        "llm_b_fallback_provider",
        "llm_c_provider",
        "llm_c_fallback_provider",
        mode="before",
    )
    @classmethod
    def _normalise_provider(cls, value: Any) -> str:
        value = (value or "").strip().lower()
        if value and value not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider '{value}'. Supported providers: "
                f"{', '.join(SUPPORTED_PROVIDERS)}."
            )
        return value

    @field_validator(
        "llm_a_model",
        "llm_a_fallback_model",
        "llm_b_model",
        "llm_b_fallback_model",
        "llm_c_model",
        "llm_c_fallback_model",
        mode="before",
    )
    @classmethod
    def _strip_model(cls, value: Any) -> str:
        return (value or "").strip()

    # ------------------------------------------------------------------ helpers
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def role_config(self, role: str) -> RoleConfig:
        role = role.upper()
        if role not in ROLES:
            raise ValueError(f"Unknown role '{role}'. Expected one of {ROLES}.")
        key = role.lower()
        return RoleConfig(
            role=role,
            provider=getattr(self, f"llm_{key}_provider"),
            model=getattr(self, f"llm_{key}_model"),
            fallback_provider=getattr(self, f"llm_{key}_fallback_provider"),
            fallback_model=getattr(self, f"llm_{key}_fallback_model"),
        )

    def api_key_for(self, provider: str) -> str | None:
        secret: SecretStr | None = getattr(self, f"{provider}_api_key", None)
        if secret is None:
            return None
        value = secret.get_secret_value().strip()
        return value or None

    def base_url_for(self, provider: str) -> str:
        return getattr(self, f"{provider}_base_url")

    def context_chars_for(self, provider: str) -> int:
        override = getattr(self, f"{provider}_context_chars", 0)
        return override if override > 0 else PROVIDER_INFO[provider]["context_chars"]

    def context_budget_for_role(self, role: str) -> int:
        """Smallest request size among the role's configured providers (so a fallback also fits)."""
        rc = self.role_config(role)
        sizes = [self.context_chars_for(p) for p in (rc.provider, rc.fallback_provider) if p]
        return min(sizes) if sizes else DEFAULT_CONTEXT_CHARS

    def secret_values(self) -> list[str]:
        values = [self.api_key_for(p) for p in SUPPORTED_PROVIDERS]
        return [v for v in values if v]

    def provider_ready(self, provider: str, model: str) -> bool:
        return bool(provider and model and self.api_key_for(provider))

    def public_status(self) -> dict[str, Any]:
        """Non-sensitive configuration summary (never contains key material)."""
        roles: dict[str, Any] = {}
        for role in ROLES:
            rc = self.role_config(role)
            roles[role] = {
                "task": ROLE_TASKS[role],
                "provider": rc.provider or None,
                "model": rc.model or None,
                "primary_ready": self.provider_ready(rc.provider, rc.model),
                "fallback_provider": rc.fallback_provider or None,
                "fallback_model": rc.fallback_model or None,
                "fallback_ready": self.provider_ready(rc.fallback_provider, rc.fallback_model),
            }
        return {
            "environment": self.app_env,
            "limits": {
                "max_upload_mb": self.max_upload_mb,
                "max_files": self.max_files,
                "max_description_chars": self.max_description_chars,
            },
            "providers": {
                p: {
                    "api_key_configured": bool(self.api_key_for(p)),
                    "label": PROVIDER_INFO[p]["label"],
                    "key_url": PROVIDER_INFO[p]["key_url"],
                    "strengths": PROVIDER_INFO[p]["strengths"],
                    "default_role": PROVIDER_INFO[p]["default_role"],
                    "suggested_models": PROVIDER_INFO[p]["suggested_models"],
                }
                for p in SUPPORTED_PROVIDERS
            },
            "roles": roles,
            "live_analysis_available": roles["A"]["primary_ready"] or roles["A"]["fallback_ready"],
            "all_roles_ready": all(
                r["primary_ready"] or r["fallback_ready"] for r in roles.values()
            ),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
