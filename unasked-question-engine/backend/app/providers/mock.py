"""Scripted provider for TESTS ONLY.

It is intentionally not registered in ``PROVIDER_CLASSES``, so it can never be
selected through environment configuration or pass as a real model.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Union

from .base import LLMProvider, LLMRequest, LLMResponse, ProviderError

Scripted = Union[str, ProviderError, Callable[[LLMRequest], str]]


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, name: str = "mock", script: list[Scripted] | None = None):
        super().__init__(api_key="mock-key-not-real", base_url="http://mock.invalid")
        self.name = name  # type: ignore[misc]
        self.script: deque[Scripted] = deque(script or [])
        self.calls: list[tuple[LLMRequest, str]] = []

    def build_request(self, request, model):  # pragma: no cover - never used
        raise NotImplementedError

    def parse_response(self, data):  # pragma: no cover - never used
        raise NotImplementedError

    def models_call(self):  # pragma: no cover - never used
        raise NotImplementedError

    @staticmethod
    def parse_models(data):  # pragma: no cover - never used
        raise NotImplementedError

    async def generate(self, request: LLMRequest, model: str) -> LLMResponse:
        self.calls.append((request, model))
        if not self.script:
            raise AssertionError("MockProvider script exhausted")
        item = self.script.popleft()
        if isinstance(item, ProviderError):
            raise item
        text = item(request) if callable(item) else item
        return LLMResponse(text=text, provider=self.name, model=model, latency_ms=1)
