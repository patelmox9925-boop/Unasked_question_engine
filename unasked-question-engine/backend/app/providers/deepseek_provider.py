"""DeepSeek. OpenAI-compatible endpoint; reasoning models do not accept JSON mode or temperature."""

from __future__ import annotations

from .openai_compat import OpenAICompatProvider


class DeepSeekProvider(OpenAICompatProvider):
    name = "deepseek"
    max_output_tokens = 8192

    @staticmethod
    def _is_reasoner(model: str) -> bool:
        return "reason" in model.lower() or model.lower().endswith("-r1")

    def supports_json_mode(self, model: str) -> bool:
        return not self._is_reasoner(model)

    def accepts_temperature(self, model: str) -> bool:
        return not self._is_reasoner(model)
