"""Routes a task to the configured model for its role (A, B or C), with fallback.

Guarantees:
* One role call = at most one successful model call (plus one optional repair
  call when the output fails schema validation). Roles are never fanned out.
* ``consulted`` lists only calls that returned schema-valid output. A model whose
  call failed is never reported as consulted.
* If every candidate fails, ``AllProvidersFailed`` is raised with a user-safe
  explanation. Nothing is fabricated.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

import httpx
from pydantic import BaseModel

from ..config import ROLES, Settings
from . import build_provider
from .base import LLMProvider, LLMRequest, ProviderError, ProviderErrorKind
from .validation import SchemaValidationError, parse_model_output

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

ProviderFactory = Callable[[str], LLMProvider]


class Attempt(BaseModel):
    role: str
    provider: str
    model: str
    ok: bool
    is_fallback: bool = False
    is_repair: bool = False
    error_kind: str | None = None
    error_message: str | None = None
    latency_ms: int | None = None


@dataclass
class RoutedResult(Generic[T]):
    data: T
    role: str
    provider: str
    model: str
    used_fallback: bool
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def consulted(self) -> bool:
        return True  # a RoutedResult only exists when a call succeeded and validated


class AllProvidersFailed(Exception):
    def __init__(self, role: str, attempts: list[Attempt], message: str):
        super().__init__(message)
        self.role = role
        self.attempts = attempts
        self.message = message


@dataclass(frozen=True)
class _Candidate:
    provider: str
    model: str
    is_fallback: bool


class LLMRouter:
    def __init__(self, settings: Settings, provider_factory: ProviderFactory | None = None,
                 client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._custom_factory = provider_factory
        self._client = client
        self._factory: ProviderFactory = provider_factory or (
            lambda name: build_provider(name, self.settings, client)
        )

    def reconfigure(self, settings: Settings) -> None:
        """Apply new settings (e.g. keys or models edited in the UI) without a restart."""
        self.settings = settings

    def candidates(self, role: str) -> list[_Candidate]:
        rc = self.settings.role_config(role)
        found: list[_Candidate] = []
        if rc.has_primary:
            found.append(_Candidate(rc.provider, rc.model, False))
        if rc.has_fallback and (rc.fallback_provider, rc.fallback_model) != (rc.provider, rc.model):
            found.append(_Candidate(rc.fallback_provider, rc.fallback_model, True))
        return found

    def role_available(self, role: str) -> bool:
        return any(self.settings.provider_ready(c.provider, c.model) for c in self.candidates(role))

    @staticmethod
    def _repair_request(request: LLMRequest, previous: str, problem: str) -> LLMRequest:
        note = (
            "\n\nYour previous reply was rejected by the validator.\n"
            f"Problem: {problem}\n"
            f"Previous reply (truncated): {previous[:3000]}\n"
            "Reply again with ONLY one corrected JSON object that matches the required schema."
        )
        return request.model_copy(update={"user": request.user + note})

    async def run(self, role: str, request: LLMRequest, output_model: type[T]) -> RoutedResult[T]:
        role = role.upper()
        if role not in ROLES:
            raise ValueError(f"Unknown role '{role}'.")
        candidates = self.candidates(role)
        attempts: list[Attempt] = []

        if not candidates:
            key = role.lower()
            raise AllProvidersFailed(
                role, attempts,
                f"Model {role} is not configured. Set LLM_{role}_PROVIDER and LLM_{role}_MODEL "
                f"(see .env.example); LLM_{key.upper()}_FALLBACK_* is optional.",
            )

        for candidate in candidates:
            try:
                provider = self._factory(candidate.provider)
            except Exception as exc:  # noqa: BLE001
                attempts.append(Attempt(role=role, provider=candidate.provider,
                                        model=candidate.model, ok=False,
                                        is_fallback=candidate.is_fallback,
                                        error_kind=ProviderErrorKind.NOT_CONFIGURED.value,
                                        error_message=f"Could not initialise provider: {type(exc).__name__}"))
                continue

            current = request
            repairs_left = self.settings.llm_max_schema_repairs
            is_repair = False
            while True:
                try:
                    response = await provider.generate(current, candidate.model)
                except ProviderError as error:
                    attempts.append(Attempt(role=role, provider=candidate.provider,
                                            model=candidate.model, ok=False,
                                            is_fallback=candidate.is_fallback, is_repair=is_repair,
                                            error_kind=error.kind.value, error_message=error.message))
                    logger.warning("Role %s: %s/%s failed (%s)", role, candidate.provider,
                                   candidate.model, error.kind.value)
                    break
                try:
                    parsed = parse_model_output(response.text, output_model)
                except SchemaValidationError as problem:
                    attempts.append(Attempt(role=role, provider=candidate.provider,
                                            model=candidate.model, ok=False,
                                            is_fallback=candidate.is_fallback, is_repair=is_repair,
                                            error_kind=ProviderErrorKind.INVALID_RESPONSE.value,
                                            error_message=problem.message[:500],
                                            latency_ms=response.latency_ms))
                    if repairs_left > 0:
                        repairs_left -= 1
                        is_repair = True
                        current = self._repair_request(request, response.text, problem.message)
                        continue
                    break
                attempts.append(Attempt(role=role, provider=candidate.provider,
                                        model=candidate.model, ok=True,
                                        is_fallback=candidate.is_fallback, is_repair=is_repair,
                                        latency_ms=response.latency_ms))
                return RoutedResult(parsed, role, candidate.provider, candidate.model,
                                    candidate.is_fallback, attempts)

        raise AllProvidersFailed(role, attempts, self._failure_message(role, attempts))

    @staticmethod
    def _failure_message(role: str, attempts: list[Attempt]) -> str:
        if not attempts:
            return f"Model {role} could not be called."
        seen: list[str] = []
        for a in attempts:
            line = f"{a.provider}/{a.model}: {a.error_kind or 'failed'}"
            if line not in seen:
                seen.append(line)
        return f"Model {role} failed on every configured provider ({'; '.join(seen)}). No analysis was produced."
