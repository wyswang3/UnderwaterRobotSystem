#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORKSPACE_ROOT="$(cd "${REPO_ROOT}/.." && pwd)"
SUPERVISOR="${REPO_ROOT}/tools/supervisor/phase0_supervisor.py"
USB_SNAPSHOT="${WORKSPACE_ROOT}/Underwater-robot-navigation/nav_core/tools/usb_serial_snapshot.py"

RUN_ROOT="${RUN_ROOT:-/tmp/phase0_supervisor_local_smoke}"
PROFILE="${PROFILE:-control_only}"
STARTUP_PROFILE="${STARTUP_PROFILE:-auto}"
START_SETTLE_S="${START_SETTLE_S:-0.2}"
POLL_INTERVAL_S="${POLL_INTERVAL_S:-0.2}"
STOP_TIMEOUT_S="${STOP_TIMEOUT_S:-5.0}"
ROV_IP="${ROV_IP:-127.0.0.1}"
STATUS_DELAY_S="${STATUS_DELAY_S:-1.0}"

if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "[ERR] python interpreter not found"
  exit 1
fi

run_cmd() {
  echo ""
  echo "+ $*"
  "$@"
}

print_usage() {
  cat <<EOF
Usage: bash tools/supervisor/run_local_teleop_smoke.sh <up|status|down|help>

Commands:
  up      Run usb snapshot, device-scan, startup-profiles, preflight, start, status
  status  Print human status and JSON status for the current RUN_ROOT
  down    Stop the latest run under RUN_ROOT and export bundle --json
  help    Show this message

Environment overrides:
  RUN_ROOT         default: /tmp/phase0_supervisor_local_smoke
  PROFILE          default: control_only
  STARTUP_PROFILE  default: auto
  START_SETTLE_S   default: 0.2
  POLL_INTERVAL_S  default: 0.2
  STOP_TIMEOUT_S   default: 5.0
  ROV_IP           default: 127.0.0.1
  STATUS_DELAY_S   default: 1.0
EOF
}

run_prepare() {
  cd "${REPO_ROOT}"
  # 这里只是把现有 teleop primary lane 的推荐顺序打包成一个 helper，不改默认语义。
  if [[ -f "${USB_SNAPSHOT}" ]]; then
    run_cmd "${PYTHON_BIN}" "${USB_SNAPSHOT}" --json
  else
    echo "[WARN] usb_serial_snapshot.py not found: ${USB_SNAPSHOT}"
  fi
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" device-scan --sample-policy off --json
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" startup-profiles --json
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" preflight     --profile "${PROFILE}"     --startup-profile "${STARTUP_PROFILE}"     --run-root "${RUN_ROOT}"
}

run_up() {
  run_prepare
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" start     --profile "${PROFILE}"     --startup-profile "${STARTUP_PROFILE}"     --detach     --run-root "${RUN_ROOT}"     --start-settle-s "${START_SETTLE_S}"     --poll-interval-s "${POLL_INTERVAL_S}"     --stop-timeout-s "${STOP_TIMEOUT_S}"
  sleep "${STATUS_DELAY_S}"
  run_status
  cat <<EOF

[NEXT] Terminal 2:
cd /home/wys/orangepi/UnderWaterRobotGCS
UROGCS_ROV_IP=${ROV_IP} bash scripts/run_tui.sh --preflight-only
UROGCS_ROV_IP=${ROV_IP} bash scripts/run_tui.sh

[NEXT] Terminal 3 (optional read-only observer):
cd /home/wys/orangepi/UnderWaterRobotGCS
UROGCS_ROV_IP=${ROV_IP} bash scripts/run_gui.sh
EOF
}

run_status() {
  cd "${REPO_ROOT}"
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" status --run-root "${RUN_ROOT}"
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" status --run-root "${RUN_ROOT}" --json
}

run_down() {
  cd "${REPO_ROOT}"
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" stop --run-root "${RUN_ROOT}" --timeout-s "${STOP_TIMEOUT_S}"
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" bundle --run-root "${RUN_ROOT}" --json
}

command="${1:-help}"
case "${command}" in
  up)
    run_up
    ;;
  status)
    run_status
    ;;
  down)
    run_down
    ;;
  help|-h|--help)
    print_usage
    ;;
  *)
    echo "[ERR] unknown command: ${command}"
    print_usage
    exit 2
    ;;
esac
