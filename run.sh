#!/usr/bin/env sh
# Start from any working directory; run.py manages .venv and dependencies.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
    exec python3 run.py "$@"
elif command -v python >/dev/null 2>&1; then
    exec python run.py "$@"
else
    echo "Python 3.9+ must be installed first." >&2
    exit 1
fi
