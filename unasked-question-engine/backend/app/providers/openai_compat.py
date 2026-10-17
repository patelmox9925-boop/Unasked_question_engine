"""Base class for providers that speak the OpenAI-style ``/chat/completions`` protocol (Groq, DeepSeek)."""

from __future__ import annotations

import re
from typing import Any

from .base import (
    HttpCall,
    LLMProvider,
    LLMRequest,
    ParsedCompletion,
    ProviderErrorKind,
)

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class OpenAICompatProvider(LLMProvider):
    max_tokens_param = "max_tokens"
    sends_temperature = True

    def supports_json_mode(self, model: str) -> bool:
        return True

    def accepts_temperature(self, model: str) -> bool:
        return self.sends_temperature

    def build_request(self, request: LLMRequest, model: str) -> HttpCall:
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            self.max_tokens_param: self.clamp_tokens(request.max_tokens),
        }
        if self.accepts_temperature(model):
            body["temperature"] = request.temperature
        if request.json_output and self.supports_json_mode(model):
            body["response_format"] = {"type": "json_object"}
        return HttpCall(
            url=f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            body=body,
        )

    def parse_response(self, data: dict[str, Any]) -> ParsedCompletion:
        choice = data["choices"][0]
        message = choice.get("message") or {}
        if message.get("refusal"):
            raise self._error(ProviderErrorKind.INVALID_RESPONSE,
                              f"{self.name} declined to answer this request.")
        # Reasoning models may inline their thoughts; only the final answer is wanted.
        text = _THINK_BLOCK.sub("", message.get("content") or "").strip()
        if not text:
            raise self._error(ProviderErrorKind.INVALID_RESPONSE,
                              f"{self.name} returned an empty response "
                              f"(finish_reason={choice.get('finish_reason')}).")
        usage = data.get("usage") or {}
        return ParsedCompletion(text, usage.get("prompt_tokens"), usage.get("completion_tokens"))

    # ---- model discovery (used by the Settings panel)
    def models_call(self) -> HttpCall:
        return HttpCall(url=f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"}, body={})

    @staticmethod
    def parse_models(data: dict[str, Any]) -> list[str]:
        return sorted({m["id"] for m in data.get("data", []) if isinstance(m, dict) and m.get("id")})
