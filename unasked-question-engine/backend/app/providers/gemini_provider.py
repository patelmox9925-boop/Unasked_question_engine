"""Google Gemini (Generative Language API) provider."""

from __future__ import annotations

from typing import Any

from .base import (
    HttpCall,
    LLMProvider,
    LLMRequest,
    ParsedCompletion,
    ProviderErrorKind,
)


class GeminiProvider(LLMProvider):
    name = "gemini"
    max_output_tokens = 8192

    def build_request(self, request: LLMRequest, model: str) -> HttpCall:
        generation_config: dict[str, Any] = {
            "temperature": request.temperature,
            "maxOutputTokens": self.clamp_tokens(request.max_tokens),
        }
        if request.json_output:
            generation_config["responseMimeType"] = "application/json"
        return HttpCall(
            url=f"{self.base_url}/models/{model}:generateContent",
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            body={
                "systemInstruction": {"parts": [{"text": request.system}]},
                "contents": [{"role": "user", "parts": [{"text": request.user}]}],
                "generationConfig": generation_config,
            },
        )

    def parse_response(self, data: dict[str, Any]) -> ParsedCompletion:
        block_reason = (data.get("promptFeedback") or {}).get("blockReason")
        if block_reason:
            raise self._error(ProviderErrorKind.INVALID_RESPONSE,
                              f"{self.name} blocked the prompt ({block_reason}).")
        candidates = data.get("candidates") or []
        if not candidates:
            raise self._error(ProviderErrorKind.INVALID_RESPONSE,
                              f"{self.name} returned no candidates.")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        # "thought" parts are the model's reasoning summary, not the answer
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise self._error(ProviderErrorKind.INVALID_RESPONSE,
                              f"{self.name} returned no text "
                              f"(finishReason={candidates[0].get('finishReason')}).")
        usage = data.get("usageMetadata") or {}
        return ParsedCompletion(text, usage.get("promptTokenCount"), usage.get("candidatesTokenCount"))

    def models_call(self) -> HttpCall:
        return HttpCall(url=f"{self.base_url}/models?pageSize=200", headers={"x-goog-api-key": self.api_key}, body={})

    @staticmethod
    def parse_models(data: dict[str, Any]) -> list[str]:
        out = []
        for m in data.get("models", []):
            if "generateContent" in (m.get("supportedGenerationMethods") or []) and m.get("name"):
                out.append(m["name"].removeprefix("models/"))
        return sorted(set(out))
