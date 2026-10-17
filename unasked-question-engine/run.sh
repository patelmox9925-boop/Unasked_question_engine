#!/usr/bin/env bash
# One-command start (macOS / Linux). Windows: use run.bat or `py run.py`.
cd "$(dirname "$0")"
for p in python3 python; do
  if command -v "$p" >/dev/null 2>&1; then exec "$p" run.py "$@"; fi
done
echo "Python 3.11+ was not found. Install it from python.org." >&2
exit 1
