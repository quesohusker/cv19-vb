#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -x "$ROOT/.venv/bin/streamlit" ]; then
  STREAMLIT="$ROOT/.venv/bin/streamlit"
elif command -v streamlit >/dev/null 2>&1; then
  STREAMLIT="streamlit"
else
  cat >&2 <<'HINT'
streamlit not found. Create the project virtualenv once:

  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt

Then re-run this script.
HINT
  exit 1
fi

exec "$STREAMLIT" run streamlit_app.py "$@"
