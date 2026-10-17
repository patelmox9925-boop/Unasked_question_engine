"""LLM provider abstraction: one interface, three integrations (Gemini, Groq, DeepSeek)."""

from __future__ import annotations

import httpx

from ..config import SUPPORTED_PROVIDERS, Settings
from .base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
    ProviderErrorKind,
)
from .gemini_provider import GeminiProvider
from .deepseek_provider import DeepSeekProvider
from .groq_provider import GroqProvider

PROVIDER_CLASSES: dict[str, type[LLMProvider]] = {
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "deepseek": DeepSeekProvider,
}
assert set(PROVIDER_CLASSES) == set(SUPPORTED_PROVIDERS)


def build_provider(name: str, settings: Settings, client: httpx.AsyncClient | None = None) -> LLMProvider:
    try:
        cls = PROVIDER_CLASSES[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported provider '{name}'.") from exc
    provider = cls(
        api_key=settings.api_key_for(name),
        base_url=settings.base_url_for(name),
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        backoff_base=settings.llm_backoff_base_seconds,
        max_retry_delay=settings.llm_max_retry_delay_seconds,
        client=client,
        secrets=settings.secret_values(),
    )
    return provider


__all__ = [
    "PROVIDER_CLASSES",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "ProviderError",
    "ProviderErrorKind",
    "build_provider",
]
