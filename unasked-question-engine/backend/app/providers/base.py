"""Shared provider interface plus the HTTP / retry / error-mapping logic.

Concrete providers only describe *how to build a request* and *how to parse a
response*; everything else (timeouts, retries, rate limits, redaction) lives here
so all providers behave identically.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel

from ..security import redact

logger = logging.getLogger(__name__)


class ProviderErrorKind(str, Enum):
    NOT_CONFIGURED = "not_configured"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    SERVER = "server"
    BAD_REQUEST = "bad_request"
    INVALID_RESPONSE = "invalid_response"


class ProviderError(Exception):
    """A provider call failed. ``str(exc)`` is safe to show to users (secrets redacted)."""

    def __init__(self, provider: str, kind: ProviderErrorKind, message: str, *,
                 status_code: int | None = None, retryable: bool = False,
                 retry_after: float | None = None):
        super().__init__(message)
        self.provider = provider
        self.kind = kind
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after = retry_after


class LLMRequest(BaseModel):
    system: str
    user: str
    temperature: float = 0.2
    max_tokens: int = 4096
    json_output: bool = True


class LLMResponse(BaseModel):
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0


@dataclass(frozen=True)
class HttpCall:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]


@dataclass(frozen=True)
class ParsedCompletion:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


Sleeper = Callable[[float], Awaitable[None]]


class LLMProvider(ABC):
    name: ClassVar[str]
    max_output_tokens: ClassVar[int] = 8192

    def __init__(self, api_key: str | None, base_url: str, *, timeout: float = 60.0,
                 max_retries: int = 2, backoff_base: float = 1.0, max_retry_delay: float = 30.0,
                 client: httpx.AsyncClient | None = None, secrets: Sequence[str] = (),
                 sleep: Sleeper = asyncio.sleep):
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.backoff_base = backoff_base
        self.max_retry_delay = max_retry_delay
        self._client = client
        self._secrets = [s for s in [*secrets, api_key] if s]
        self._sleep = sleep

    # ------------------------------------------------------------- to implement
    @abstractmethod
    def build_request(self, request: LLMRequest, model: str) -> HttpCall: ...

    @abstractmethod
    def parse_response(self, data: dict[str, Any]) -> ParsedCompletion: ...

    @abstractmethod
    def models_call(self) -> HttpCall: ...

    @staticmethod
    @abstractmethod
    def parse_models(data: dict[str, Any]) -> list[str]: ...

    # ------------------------------------------------------------------ helpers
    @classmethod
    def clamp_tokens(cls, requested: int) -> int:
        return max(1, min(requested, cls.max_output_tokens))

    @property
    def api_key(self) -> str:
        assert self._api_key, "api key checked before use"
        return self._api_key

    def _clean(self, text: str, limit: int = 300) -> str:
        return redact(text, self._secrets)[:limit]

    def _error(self, kind: ProviderErrorKind, message: str, **kw: Any) -> ProviderError:
        return ProviderError(self.name, kind, self._clean(message, 500), **kw)

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        raw = response.headers.get("retry-after")
        if not raw:
            return None
        try:
            return max(0.0, float(raw))
        except ValueError:
            return None

    def _error_for_status(self, response: httpx.Response) -> ProviderError:
        status = response.status_code
        try:
            body = response.text
        except Exception:  # noqa: BLE001
            body = ""
        snippet = self._clean(body)
        if status == 429:
            return self._error(ProviderErrorKind.RATE_LIMIT,
                               f"{self.name} rate limit reached (HTTP 429). {snippet}",
                               status_code=status, retryable=True,
                               retry_after=self._retry_after(response))
        if status in (401, 403):
            return self._error(ProviderErrorKind.AUTH,
                               f"{self.name} rejected the credentials (HTTP {status}). "
                               "Check the API key and model access.",
                               status_code=status)
        if status >= 500:
            return self._error(ProviderErrorKind.SERVER,
                               f"{self.name} had a server error (HTTP {status}). {snippet}",
                               status_code=status, retryable=True,
                               retry_after=self._retry_after(response))
        return self._error(ProviderErrorKind.BAD_REQUEST,
                           f"{self.name} rejected the request (HTTP {status}). {snippet}",
                           status_code=status)

    async def _post_once(self, client: httpx.AsyncClient, call: HttpCall) -> dict[str, Any]:
        try:
            if call.body:
                response = await client.post(call.url, headers=call.headers, json=call.body)
            else:
                response = await client.get(call.url, headers=call.headers)
        except httpx.TimeoutException as exc:
            raise self._error(ProviderErrorKind.TIMEOUT,
                              f"{self.name} did not respond within {self.timeout:g}s.",
                              retryable=True) from exc
        except httpx.HTTPError as exc:
            raise self._error(ProviderErrorKind.NETWORK,
                              f"Could not reach {self.name} ({type(exc).__name__}).",
                              retryable=True) from exc
        if response.status_code >= 400:
            raise self._error_for_status(response)
        try:
            data = response.json()
        except ValueError as exc:
            raise self._error(ProviderErrorKind.INVALID_RESPONSE,
                              f"{self.name} returned a response that was not valid JSON.") from exc
        if not isinstance(data, dict):
            raise self._error(ProviderErrorKind.INVALID_RESPONSE,
                              f"{self.name} returned an unexpected response shape.")
        return data

    def _delay(self, attempt: int, error: ProviderError) -> float:
        if error.retry_after is not None:
            delay = error.retry_after
        else:
            delay = self.backoff_base * (2 ** attempt) + random.uniform(0, self.backoff_base / 4)
        return min(delay, self.max_retry_delay)

    # --------------------------------------------------------------- public API
    async def generate(self, request: LLMRequest, model: str) -> LLMResponse:
        if not self._api_key:
            raise self._error(ProviderErrorKind.NOT_CONFIGURED,
                              f"No API key is configured for {self.name}.")
        if not model:
            raise self._error(ProviderErrorKind.NOT_CONFIGURED,
                              f"No model is configured for {self.name}.")
        call = self.build_request(request, model)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        started = time.monotonic()
        try:
            last_error: ProviderError | None = None
            for attempt in range(self.max_retries + 1):
                try:
                    data = await self._post_once(client, call)
                    try:
                        parsed = self.parse_response(data)
                    except ProviderError:
                        raise
                    except Exception as exc:  # noqa: BLE001 - malformed provider payload
                        raise self._error(ProviderErrorKind.INVALID_RESPONSE,
                                          f"{self.name} response was missing expected fields.") from exc
                    return LLMResponse(
                        text=parsed.text, provider=self.name, model=model,
                        input_tokens=parsed.input_tokens, output_tokens=parsed.output_tokens,
                        latency_ms=int((time.monotonic() - started) * 1000),
                    )
                except ProviderError as error:
                    last_error = error
                    if not error.retryable or attempt >= self.max_retries:
                        raise
                    delay = self._delay(attempt, error)
                    logger.warning("%s call failed (%s); retry %d/%d in %.1fs", self.name,
                                   error.kind.value, attempt + 1, self.max_retries, delay)
                    await self._sleep(delay)
            raise last_error or self._error(ProviderErrorKind.NETWORK, "Call failed.")
        finally:
            if owns_client:
                await client.aclose()

    async def list_models(self) -> list[str]:
        """Model ids this key can use (a cheap call that also proves the key works)."""
        if not self._api_key:
            raise self._error(ProviderErrorKind.NOT_CONFIGURED, f"No API key is configured for {self.name}.")
        call = self.models_call()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=min(self.timeout, 20.0))
        try:
            data = await self._post_once(client, call)
            try:
                return self.parse_models(data)
            except Exception as exc:  # noqa: BLE001
                raise self._error(ProviderErrorKind.INVALID_RESPONSE,
                                  f"{self.name} returned an unexpected model list.") from exc
        finally:
            if owns_client:
                await client.aclose()
