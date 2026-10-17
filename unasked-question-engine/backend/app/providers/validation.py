"""Strict validation of raw model text against a Pydantic schema."""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?```\s*$", re.DOTALL)


class SchemaValidationError(Exception):
    """Model output was not valid JSON or did not match the schema."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def extract_json_object(raw: str) -> dict:
    """Pull a single JSON object out of model text (tolerates code fences / preamble)."""
    text = raw.strip()
    fenced = _FENCE_RE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    candidates = [0] if text.startswith("{") else []
    candidates += [m.start() for m in re.finditer(r"\{", text) if m.start() != 0]
    for start in candidates:
        try:
            value, _ = decoder.raw_decode(text[start:])
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    raise SchemaValidationError("The response did not contain a valid JSON object.")


def summarise_errors(error: ValidationError, limit: int = 6) -> str:
    items = []
    for item in error.errors()[:limit]:
        location = ".".join(str(p) for p in item["loc"]) or "(root)"
        items.append(f"{location}: {item['msg']}")
    extra = len(error.errors()) - limit
    if extra > 0:
        items.append(f"...and {extra} more")
    return "; ".join(items)


def parse_model_output(raw: str, model_cls: type[T]) -> T:
    data = extract_json_object(raw)
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise SchemaValidationError(
            f"JSON did not match the required schema: {summarise_errors(exc)}"
        ) from exc
