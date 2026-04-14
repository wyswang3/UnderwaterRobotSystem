#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "[ERR] please source this file instead of executing it"
  echo "[INFO] usage: source ./enter_py311.sh"
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_PY311_VENV="${URO_PROJECT_PY311_VENV:-${HOME}/venvs/py311}"
ACTIVATE_SCRIPT="${PROJECT_PY311_VENV}/bin/activate"
PYTHON_BIN="${PROJECT_PY311_VENV}/bin/python"

if [[ ! -f "${ACTIVATE_SCRIPT}" ]]; then
  echo "[ERR] py311 virtualenv activate script not found: ${ACTIVATE_SCRIPT}"
  echo "[INFO] override with: export URO_PROJECT_PY311_VENV=<venv_root>"
  return 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[ERR] py311 python not found: ${PYTHON_BIN}"
  return 1
fi

cd "${REPO_ROOT}"
# shellcheck disable=SC1090
source "${ACTIVATE_SCRIPT}"
export URO_SUPERVISOR_PYTHON_BIN="${PYTHON_BIN}"

echo "[INFO] Project root: ${REPO_ROOT}"
echo "[INFO] Activated venv: ${VIRTUAL_ENV:-${PROJECT_PY311_VENV}}"
echo "[INFO] URO_SUPERVISOR_PYTHON_BIN: ${URO_SUPERVISOR_PYTHON_BIN}"
echo "[INFO] Python version: $(python --version 2>&1)"
echo "[INFO] Python path: $(command -v python)"
