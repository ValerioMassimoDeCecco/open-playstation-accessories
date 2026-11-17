#!/usr/bin/env bash
# PlayStation Accessories - Open Source Edition (V3.0)
# Launcher per macOS e Linux:  ./run.sh
set -u

cd "$(dirname "$0")" || exit 1

PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "Errore: Python 3.8 o superiore non trovato."
    echo "Su macOS installalo da https://www.python.org/downloads/ (oppure: brew install python)."
    exit 1
fi

exec "$PYTHON_BIN" app/main.py "$@"
