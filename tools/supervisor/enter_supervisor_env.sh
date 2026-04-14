#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "[ERR] please source this file instead of executing it"
  echo "[INFO] usage: source tools/supervisor/enter_supervisor_env.sh"
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

select_python() {
  if [[ -n "${URO_SUPERVISOR_PYTHON_BIN:-}" ]]; then
    if [[ ! -x "${URO_SUPERVISOR_PYTHON_BIN}" ]]; then
      echo "[ERR] URO_SUPERVISOR_PYTHON_BIN is not executable: ${URO_SUPERVISOR_PYTHON_BIN}"
      return 1
    fi
    return 0
  fi
  if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    URO_SUPERVISOR_PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    URO_SUPERVISOR_PYTHON_BIN="$(command -v python3)"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    URO_SUPERVISOR_PYTHON_BIN="$(command -v python)"
    return 0
  fi
  echo "[ERR] python interpreter not found"
  return 1
}

select_python
export URO_SUPERVISOR_PYTHON_BIN

if [[ -f "${REPO_ROOT}/.venv/bin/activate" && "${URO_SUPERVISOR_PYTHON_BIN}" == "${REPO_ROOT}/.venv/bin/python" ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.venv/bin/activate"
fi

echo "[INFO] Supervisor root: ${REPO_ROOT}"
echo "[INFO] URO_SUPERVISOR_PYTHON_BIN: ${URO_SUPERVISOR_PYTHON_BIN}"
echo "[INFO] Python version: $("${URO_SUPERVISOR_PYTHON_BIN}" --version 2>&1)"
