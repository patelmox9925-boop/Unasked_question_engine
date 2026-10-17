"""Minimal, safe .env editing used by the Settings page.

* Keeps comments, ordering and unrelated lines.
* Only writes values that match a conservative pattern (no spaces, quotes or newlines), so a
  pasted value can never inject extra settings.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_VALUE_OK = re.compile(r"^[A-Za-z0-9._\-:/+=@]{0,400}$")
_KEY_OK = re.compile(r"^[A-Z][A-Z0-9_]{2,60}$")


class EnvValueError(ValueError):
    pass


def validate_value(name: str, value: str) -> str:
    value = value.strip()
    if not _VALUE_OK.match(value):
        raise EnvValueError(f"{name}: only letters, digits and . _ - : / + = @ are allowed (no spaces or quotes).")
    return value


def update_env_file(path: Path, updates: dict[str, str | None], *, apply_to_environ: bool = True) -> None:
    """Set (or, with ``None``/empty, clear) the given variables in ``path`` and in ``os.environ``."""
    clean: dict[str, str] = {}
    for name, value in updates.items():
        if not _KEY_OK.match(name):
            raise EnvValueError(f"Invalid setting name: {name}")
        clean[name] = validate_value(name, value or "")

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(clean)
    out: list[str] = []
    for line in lines:
        match = re.match(r"^\s*([A-Z][A-Z0-9_]*)\s*=", line)
        if match and match.group(1) in remaining:
            name = match.group(1)
            out.append(f"{name}={remaining.pop(name)}")
        else:
            out.append(line)
    if remaining:
        if out and out[-1].strip():
            out.append("")
        out.extend(f"{name}={value}" for name, value in remaining.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)  # keys live here
    except OSError:  # pragma: no cover - not supported on every platform
        pass
    tmp.replace(path)

    if apply_to_environ:  # real environment variables outrank .env, so keep them in sync
        for name, value in clean.items():
            if value:
                os.environ[name] = value
            else:
                os.environ.pop(name, None)
