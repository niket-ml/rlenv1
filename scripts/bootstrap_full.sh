#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="${PROJECT_ROOT}/.venv"

"${PROJECT_ROOT}/scripts/bootstrap_local.sh"
"${VENV_PATH}/bin/python" -m pip install --no-build-isolation \
  "${PROJECT_ROOT}[science,notebook,rl]"
"${VENV_PATH}/bin/uc-bench" doctor

echo
echo "Full UC-Bench environment is ready, including scientific, notebook execution, and RL layers."
