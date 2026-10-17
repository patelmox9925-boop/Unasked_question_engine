"""Groq (fast open-model inference). OpenAI-compatible endpoint."""

from __future__ import annotations

from .openai_compat import OpenAICompatProvider


class GroqProvider(OpenAICompatProvider):
    name = "groq"
    max_tokens_param = "max_completion_tokens"
    max_output_tokens = 8000
