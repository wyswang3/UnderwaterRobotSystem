#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORKSPACE_ROOT="$(cd "${REPO_ROOT}/.." && pwd)"
SUPERVISOR="${REPO_ROOT}/tools/supervisor/phase0_supervisor.py"
USB_SNAPSHOT="${WORKSPACE_ROOT}/Underwater-robot-navigation/nav_core/tools/usb_serial_snapshot.py"
GCS_ROOT="${WORKSPACE_ROOT}/UnderWaterRobotGCS"
GCS_TUI_LAUNCHER="${GCS_ROOT}/scripts/run_tui.sh"
GCS_GUI_LAUNCHER="${GCS_ROOT}/scripts/run_gui.sh"
HELPER_CMD_HINT="bash tools/supervisor/run_local_teleop_smoke.sh"

RUN_ROOT="${RUN_ROOT:-/tmp/phase0_supervisor_local_smoke}"
PROFILE="${PROFILE:-control_only}"
STARTUP_PROFILE="${STARTUP_PROFILE:-auto}"
START_SETTLE_S="${START_SETTLE_S:-0.2}"
POLL_INTERVAL_S="${POLL_INTERVAL_S:-0.2}"
STOP_TIMEOUT_S="${STOP_TIMEOUT_S:-5.0}"
ROV_IP="${ROV_IP:-127.0.0.1}"
STATUS_DELAY_S="${STATUS_DELAY_S:-1.0}"
REAL_PWM="${REAL_PWM:-0}"
PROJECT_PY311_VENV="${URO_PROJECT_PY311_VENV:-${HOME}/venvs/py311}"

if [[ -n "${URO_SUPERVISOR_PYTHON_BIN:-}" ]]; then
  if [[ ! -x "${URO_SUPERVISOR_PYTHON_BIN}" ]]; then
    echo "[ERR] URO_SUPERVISOR_PYTHON_BIN is not executable: ${URO_SUPERVISOR_PYTHON_BIN}"
    exit 1
  fi
  PYTHON_BIN="${URO_SUPERVISOR_PYTHON_BIN}"
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
elif [[ -x "${PROJECT_PY311_VENV}/bin/python" ]]; then
  PYTHON_BIN="${PROJECT_PY311_VENV}/bin/python"
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

set_real_pwm_mode() {
  REAL_PWM="$1"
}

print_pwm_mode_banner() {
  echo ""
  if [[ "${REAL_PWM}" == "1" ]]; then
    echo "[INFO] PWM backend mode: STM32"
    echo "[INFO] helper will pass --real-pwm; pwm_control_program will not append --pwm-dummy."
  else
    echo "[INFO] PWM backend mode: DUMMY"
    echo "[INFO] helper default keeps --pwm-dummy; TUI commands can reach pwm_control_program, but no packets will be sent to STM32."
  fi
}

print_usage() {
  cat <<EOF
Usage: bash tools/supervisor/run_local_teleop_smoke.sh <command>

Commands:
  up            启动车端 dummy backend，并打印下一步
  up-real       启动车端真实 STM32 PWM 输出
  restart       先停后起，相当于 down + up
  restart-real  先停后起真实 PWM，相当于 down + up-real
  status        打印当前 RUN_ROOT 的 human status 和 JSON status
  doctor        打印更短的排障摘要和建议下一步
  teleop        同机开发捷径：启动本机工作区里的 GCS TUI，自动带入 ROV_IP
  gui           同机开发捷径：启动本机工作区里的 GCS GUI，自动带入 ROV_IP
  down          停止当前 RUN_ROOT 的最新 run 并导出 bundle --json
  help          显示帮助

Environment overrides:
  RUN_ROOT         default: /tmp/phase0_supervisor_local_smoke
  PROFILE          default: control_only
  STARTUP_PROFILE  default: auto
  START_SETTLE_S   default: 0.2
  POLL_INTERVAL_S  default: 0.2
  STOP_TIMEOUT_S   default: 5.0
  ROV_IP           default: 127.0.0.1
  STATUS_DELAY_S   default: 1.0
  REAL_PWM         default: 0
  URO_PROJECT_PY311_VENV  default: \$HOME/venvs/py311
  URO_SUPERVISOR_PYTHON_BIN  optional explicit interpreter path for supervisor/helper commands

Recommended operator flow:
  1. ${HELPER_CMD_HINT} up-real
  2. ${HELPER_CMD_HINT} doctor
  3. 在上位机的 UnderWaterRobotGCS 仓根执行: UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_tui.sh
  4. 可选只读观察: 在上位机的 UnderWaterRobotGCS 仓根执行: UROGCS_ROV_IP=<OrangePi_IP> bash scripts/run_gui.sh
  5. ${HELPER_CMD_HINT} down

Same-workspace development shortcuts:
  1. ROV_IP=<OrangePi_IP> ${HELPER_CMD_HINT} teleop
  2. ROV_IP=<OrangePi_IP> ${HELPER_CMD_HINT} gui

Notes:
  1. teleop/gui 只适用于本机同时检出 UnderWaterRobotGCS 的联调工作区。
  2. 实际分机部署时，车端命令在 OrangePi 上执行，GCS 命令在上位机的 UnderWaterRobotGCS 仓执行。
EOF
}

ensure_gcs_launcher() {
  local launcher="$1"
  if [[ ! -f "${launcher}" ]]; then
    echo "[ERR] GCS launcher not found: ${launcher}"
    echo "[INFO] teleop/gui shortcuts only work when UnderWaterRobotGCS is checked out beside this repo on the same machine"
    echo "[INFO] for split-host deployment, run GCS from the upper computer's UnderWaterRobotGCS repo"
    return 1
  fi
}

run_stop_if_present() {
  cd "${REPO_ROOT}"
  local output
  local rc=0
  local -a stop_cmd=(
    "${PYTHON_BIN}" "${SUPERVISOR}" stop
    --run-root "${RUN_ROOT}"
    --timeout-s "${STOP_TIMEOUT_S}"
  )
  echo ""
  echo "+ ${stop_cmd[*]}"
  set +e
  output="$("${stop_cmd[@]}" 2>&1)"
  rc=$?
  set -e
  if [[ -n "${output}" ]]; then
    printf '%s\n' "${output}"
  fi
  if [[ ${rc} -eq 0 ]]; then
    run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" bundle --run-root "${RUN_ROOT}" --json
    return 0
  fi
  if [[ "${output}" == *"no supervisor run found"* ]]; then
    echo "[INFO] no existing supervisor run found under RUN_ROOT=${RUN_ROOT}"
    return 0
  fi
  return "${rc}"
}

print_next_steps() {
  cat <<EOF

[NEXT] Terminal 2:
在上位机的 UnderWaterRobotGCS 仓根执行:
UROGCS_ROV_IP=${ROV_IP} bash scripts/run_tui.sh

[NEXT] Terminal 3 (optional read-only observer):
在上位机的 UnderWaterRobotGCS 仓根执行:
UROGCS_ROV_IP=${ROV_IP} bash scripts/run_gui.sh

[DEV] Same-workspace shortcuts on a machine that also has UnderWaterRobotGCS:
ROV_IP=${ROV_IP} ${HELPER_CMD_HINT} teleop
ROV_IP=${ROV_IP} ${HELPER_CMD_HINT} gui
EOF
}

run_prepare() {
  cd "${REPO_ROOT}"
  local -a extra_args=()
  print_pwm_mode_banner
  if [[ "${REAL_PWM}" == "1" ]]; then
    extra_args+=(--real-pwm)
  fi
  # 这里只是把现有 teleop primary lane 的推荐顺序打包成一个 helper，不改默认 authority 语义。
  if [[ -f "${USB_SNAPSHOT}" ]]; then
    run_cmd "${PYTHON_BIN}" "${USB_SNAPSHOT}" --json
  else
    echo "[WARN] usb_serial_snapshot.py not found: ${USB_SNAPSHOT}"
  fi
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" device-scan --sample-policy off --json
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" startup-profiles --json
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" preflight \
    --profile "${PROFILE}" \
    --startup-profile "${STARTUP_PROFILE}" \
    --run-root "${RUN_ROOT}" \
    "${extra_args[@]}"
}

run_up() {
  run_prepare
  local -a extra_args=()
  if [[ "${REAL_PWM}" == "1" ]]; then
    extra_args+=(--real-pwm)
  fi
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" start \
    --profile "${PROFILE}" \
    --startup-profile "${STARTUP_PROFILE}" \
    --detach \
    --run-root "${RUN_ROOT}" \
    --start-settle-s "${START_SETTLE_S}" \
    --poll-interval-s "${POLL_INTERVAL_S}" \
    --stop-timeout-s "${STOP_TIMEOUT_S}" \
    "${extra_args[@]}"
  sleep "${STATUS_DELAY_S}"
  run_status
  print_next_steps
}

run_status() {
  cd "${REPO_ROOT}"
  print_pwm_mode_banner
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" status --run-root "${RUN_ROOT}"
  run_cmd "${PYTHON_BIN}" "${SUPERVISOR}" status --run-root "${RUN_ROOT}" --json
}

run_down() {
  run_stop_if_present
}

run_restart() {
  run_stop_if_present
  run_up
}

run_doctor() {
  cd "${REPO_ROOT}"
  local output
  local rc=0
  local -a status_cmd=(
    "${PYTHON_BIN}" "${SUPERVISOR}" status
    --run-root "${RUN_ROOT}"
    --json
  )
  echo ""
  echo "+ ${status_cmd[*]}"
  set +e
  output="$("${status_cmd[@]}" 2>&1)"
  rc=$?
  set -e
  if [[ ${rc} -ne 0 ]]; then
    if [[ "${output}" == *"no supervisor run found"* ]]; then
      cat <<EOF
[WARN] no supervisor run found under RUN_ROOT=${RUN_ROOT}
[NEXT] dummy bring-up: ${HELPER_CMD_HINT} up
[NEXT] real STM32 bring-up: ${HELPER_CMD_HINT} up-real
[NEXT] after vehicle side is up, open TUI with: ROV_IP=${ROV_IP} ${HELPER_CMD_HINT} teleop
EOF
      return 0
    fi
    printf '%s\n' "${output}"
    return "${rc}"
  fi
  URO_STATUS_JSON="${output}" URO_HELPER_CMD="${HELPER_CMD_HINT}" URO_ROV_IP="${ROV_IP}" "${PYTHON_BIN}" - <<'PY'
import json
import os
from pathlib import Path

data = json.loads(os.environ["URO_STATUS_JSON"])
helper = os.environ.get("URO_HELPER_CMD", "bash tools/supervisor/run_local_teleop_smoke.sh")
rov_ip = os.environ.get("URO_ROV_IP", "127.0.0.1")
state = str(data.get("supervisor_state") or "unknown")
processes = list(data.get("processes") or [])
capability = data.get("capability") or {}
motion_info = data.get("motion_info") or {}
operator_lane = data.get("operator_lane") or {}
running = [proc for proc in processes if str(proc.get("state")) == "running"]
not_running = [proc for proc in processes if str(proc.get("state")) != "running"]
overall_ok = state == "running" and not not_running
status_tag = "OK" if overall_ok else "WARN"
print(
    f"[{status_tag}] profile={data.get('profile')} state={state} "
    f"pwm_backend={data.get('pwm_backend')} capability={capability.get('level')} "
    f"motion_info={motion_info.get('state')}"
)
print(
    f"[INFO] operator_lane={operator_lane.get('name')} "
    f"teleop_state={operator_lane.get('teleop_state')} "
    f"recommended_tui_ip={rov_ip}"
)
if processes:
    print(f"[INFO] processes_running={len(running)}/{len(processes)}")
if not_running:
    parts = [f"{proc.get('name')}={proc.get('state')}" for proc in not_running]
    print("[WARN] process attention: " + ", ".join(parts))
else:
    print("[INFO] all expected processes are running")

fault_event = str(data.get("last_fault_event") or "none")
fault_message = str(data.get("last_fault_message") or "no fault recorded")
fault_process = data.get("last_fault_process_name") or "-"
if fault_event not in {"none", "supervisor_stopped"}:
    print(f"[WARN] last_fault event={fault_event} process={fault_process} message={fault_message}")
else:
    print(f"[INFO] last_fault event={fault_event} message={fault_message}")

child_logs_dir = data.get("child_logs_dir")
if child_logs_dir:
    run_dir = Path(child_logs_dir).parent
    print(f"[INFO] run_dir={run_dir}")
    print(f"[INFO] last_fault_summary={run_dir / 'last_fault_summary.txt'}")

if str(data.get("pwm_backend")) == "dummy":
    print(f"[CHECK] real STM32 output is OFF. Use {helper} restart-real when real thrust output is required.")
if not overall_ok:
    print(f"[NEXT] recover with: {helper} restart")
    print(f"[NEXT] if it still fails, stop and collect logs with: {helper} down")
else:
    print(f"[NEXT] upper computer TUI: UROGCS_ROV_IP={rov_ip} bash scripts/run_tui.sh")
    print(f"[DEV] same-workspace shortcut: ROV_IP={rov_ip} {helper} teleop")
if motion_info.get("state") not in {"ready", "not_enabled_for_capability"}:
    print("[CHECK] motion info is not ready; if nav preview is expected, inspect nav side and GCS Motion Info/Fault Summary.")
PY
}

run_teleop() {
  ensure_gcs_launcher "${GCS_TUI_LAUNCHER}"
  cd "${GCS_ROOT}"
  echo ""
  echo "[INFO] Launching GCS TUI via same-workspace dev shortcut with UROGCS_ROV_IP=${ROV_IP}"
  UROGCS_ROV_IP="${ROV_IP}" bash "${GCS_TUI_LAUNCHER}"
}

run_gui() {
  ensure_gcs_launcher "${GCS_GUI_LAUNCHER}"
  cd "${GCS_ROOT}"
  echo ""
  echo "[INFO] Launching GCS GUI via same-workspace dev shortcut with UROGCS_ROV_IP=${ROV_IP}"
  UROGCS_ROV_IP="${ROV_IP}" bash "${GCS_GUI_LAUNCHER}"
}

command="${1:-help}"
if [[ $# -gt 0 ]]; then
  shift
fi
if [[ $# -ne 0 ]]; then
  echo "[ERR] Unsupported arguments for command ${command}: $*"
  print_usage
  exit 2
fi

case "${command}" in
  up)
    set_real_pwm_mode 0
    run_up
    ;;
  up-real)
    set_real_pwm_mode 1
    run_up
    ;;
  restart)
    set_real_pwm_mode 0
    run_restart
    ;;
  restart-real)
    set_real_pwm_mode 1
    run_restart
    ;;
  status)
    run_status
    ;;
  doctor)
    run_doctor
    ;;
  teleop)
    run_teleop
    ;;
  gui|observe)
    run_gui
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
