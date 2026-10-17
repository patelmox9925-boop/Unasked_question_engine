"""Helpers that keep secrets out of logs, errors and API responses."""

from __future__ import annotations

import re
from collections.abc import Iterable

REDACTED = "[REDACTED]"

_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)\b(x-api-key|x-goog-api-key|api[_-]?key)\b(\s*[:=]\s*)\S+"),
]


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Remove known secret values and common API-key shapes from ``text``."""
    if not text:
        return text
    for secret in secrets:
        if secret and len(secret) >= 8:
            text = text.replace(secret, REDACTED)
    for pattern in _PATTERNS[:3]:
        text = pattern.sub(REDACTED, text)
    text = _PATTERNS[3].sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    return text
