#!/usr/bin/env python3
"""Cross-platform launcher (Windows, macOS, Linux).

    python run.py            # or: py run.py   (Windows)   /   python3 run.py

Creates .venv, installs backend/requirements.txt, serves the app on http://127.0.0.1:8000.
Set PORT=9000 to use another port. Use --reinstall to force a fresh dependency install.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQ = ROOT / "backend" / "requirements.txt"
STAMP = VENV / ".requirements-installed"
MIN_PYTHON = (3, 11)


def fail(message: str) -> None:
    print(f"\nERROR: {message}\n", file=sys.stderr)
    sys.exit(1)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(cmd: list[str], **kw) -> None:
    result = subprocess.run(cmd, **kw)
    if result.returncode != 0:
        fail(f"Command failed ({result.returncode}): {' '.join(map(str, cmd))}")


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def main() -> None:
    if sys.version_info < MIN_PYTHON:
        fail(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is required, but this is "
            f"{sys.version_info.major}.{sys.version_info.minor}. Install a newer Python from python.org and retry."
        )
    port = int(os.environ.get("PORT", "8000"))
    if not port_free(port):
        fail(f"Port {port} is already in use. Close the other program, or run with PORT=8001 (set PORT=8001 on Windows).")

    if not venv_python().exists():
        print("Creating virtual environment (.venv)...")
        run([sys.executable, "-m", "venv", str(VENV)])
    py = str(venv_python())

    if "--reinstall" in sys.argv or not STAMP.exists() or STAMP.stat().st_mtime < REQ.stat().st_mtime:
        print("Installing dependencies (first run takes a minute)...")
        run([py, "-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", "pip"])
        run([py, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(REQ)])
        STAMP.write_text("ok")

    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        print("NOTE: frontend/dist is missing, so only the API will run. Build the UI with: cd frontend && npm install && npm run build")

    print(f"\nOpen http://127.0.0.1:{port}   (Ctrl+C to stop)\n")
    try:
        subprocess.run([py, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT / "backend")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
