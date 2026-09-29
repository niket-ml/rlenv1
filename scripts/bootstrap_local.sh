#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="${PROJECT_ROOT}/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  if [[ -x /opt/homebrew/opt/python@3.11/bin/python3.11 ]]; then
    PYTHON_BIN=/opt/homebrew/opt/python@3.11/bin/python3.11
  else
    echo "Python 3.11 is required. Set PYTHON_BIN to a compatible interpreter." >&2
    exit 1
  fi
fi

if [[ ! -x "${VENV_PATH}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_PATH}"
fi

"${VENV_PATH}/bin/python" -m pip install --no-build-isolation "${PROJECT_ROOT}[dev]"

"${VENV_PATH}/bin/uc-bench" doctor

echo
echo "UC-Bench is ready. Activate it with:"
echo "  source '${VENV_PATH}/bin/activate'"
