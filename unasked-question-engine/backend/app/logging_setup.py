"""Logging configuration with automatic secret redaction."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from .security import redact


_current_provider: Callable[[], Iterable[str]] = lambda: []


class RedactingFilter(logging.Filter):
    """Redacts the *current* secrets (the provider can change when settings are edited at runtime)."""

    def __init__(self, secrets_provider: Callable[[], Iterable[str]] | None = None):
        super().__init__()
        self._secrets_provider = secrets_provider

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - never let logging crash the app
            return True
        provider = self._secrets_provider or _current_provider
        record.msg = redact(message, list(provider()))
        record.args = ()
        return True


def setup_logging(level: str, secrets_provider: Callable[[], Iterable[str]]) -> None:
    global _current_provider
    _current_provider = secrets_provider
    root = logging.getLogger()
    root.setLevel(level.upper())
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    for handler in root.handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(RedactingFilter())
