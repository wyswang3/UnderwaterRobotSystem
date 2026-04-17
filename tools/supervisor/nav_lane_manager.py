#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent
NAV_CORE_ROOT = WORKSPACE_ROOT / 'Underwater-robot-navigation' / 'nav_core'
CTRL_ROOT = WORKSPACE_ROOT / 'OrangePi_STM32_for_ROV'

DEFAULT_NAV_CFG = NAV_CORE_ROOT / 'config' / 'nav_daemon.yaml'
DEFAULT_ESKF_CFG = NAV_CORE_ROOT / 'config' / 'eskf.yaml'
DEFAULT_NAV_BIN = NAV_CORE_ROOT / 'build' / 'bin' / 'uwnav_navd'
DEFAULT_NAV_VIEW_BIN = CTRL_ROOT / 'build' / 'bin' / 'nav_viewd'
DEFAULT_STATE_PATH = REPO_ROOT / 'reports' / 'nav_lane_manager' / 'state.json'


def wall_time_now() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime())


def safe_write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def process_group_signal(pid: int, sig: int) -> None:
    if pid <= 0:
        return
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        return


def wait_for_pid_exit(pid: int, timeout_s: float) -> bool:
    deadline = time.time() + max(0.0, timeout_s)
    while time.time() < deadline:
        if not pid_is_running(pid):
            return True
        time.sleep(0.1)
    return not pid_is_running(pid)


def trim_comment(line: str) -> str:
    comment_pos = line.find('#')
    if comment_pos >= 0:
        line = line[:comment_pos]
    return line.rstrip('\n')


def read_dvl_enable(nav_cfg: Path) -> bool:
    lines = nav_cfg.read_text(encoding='utf-8').splitlines()
    in_dvl = False
    for raw in lines:
        line = trim_comment(raw)
        stripped = line.strip()
        if not stripped:
            continue
        if raw and raw[0] not in {' ', '\t'} and stripped.endswith(':'):
            in_dvl = stripped == 'dvl:'
            continue
        if in_dvl and stripped.startswith('enable:'):
            value = stripped.split(':', 1)[1].strip().lower()
            return value in {'true', '1', 'yes', 'on'}
    raise RuntimeError(f'dvl.enable not found in {nav_cfg}')


def write_dvl_enable(nav_cfg: Path, enabled: bool) -> bool:
    lines = nav_cfg.read_text(encoding='utf-8').splitlines()
    in_dvl = False
    updated = False
    for idx, raw in enumerate(lines):
        line = trim_comment(raw)
        stripped = line.strip()
        if not stripped:
            continue
        if raw and raw[0] not in {' ', '\t'} and stripped.endswith(':'):
            in_dvl = stripped == 'dvl:'
            continue
        if in_dvl and stripped.startswith('enable:'):
            indent = raw[: len(raw) - len(raw.lstrip(' '))]
            current = stripped.split(':', 1)[1].strip().lower() in {'true', '1', 'yes', 'on'}
            lines[idx] = f"{indent}enable: {'true' if enabled else 'false'}"
            updated = current != enabled
            break
    else:
        raise RuntimeError(f'dvl.enable not found in {nav_cfg}')

    nav_cfg.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return updated


def read_state(state_path: Path) -> dict:
    state = load_json(state_path)
    state.setdefault('dvl_policy_enabled', False)
    state.setdefault('navd_pid', 0)
    state.setdefault('nav_viewd_pid', 0)
    state.setdefault('updated_wall_time', '')
    state.setdefault('last_error', '')
    return state


def build_state(*, dvl_policy_enabled: bool, navd_pid: int, nav_viewd_pid: int, last_error: str = '') -> dict:
    return {
        'dvl_policy_enabled': bool(dvl_policy_enabled),
        'navd_pid': int(navd_pid),
        'nav_viewd_pid': int(nav_viewd_pid),
        'navd_running': pid_is_running(navd_pid),
        'nav_viewd_running': pid_is_running(nav_viewd_pid),
        'updated_wall_time': wall_time_now(),
        'last_error': last_error,
        'nav_config_path': str(DEFAULT_NAV_CFG),
    }


def detect_untracked_nav_processes(excluded_pids: set[int]) -> list[str]:
    try:
        proc = subprocess.run(
            ['pgrep', '-af', 'uwnav_navd|nav_viewd'],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []

    if proc.returncode not in {0, 1}:
        return []

    conflicts: list[str] = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(maxsplit=1)
        try:
            pid = int(parts[0])
        except (ValueError, IndexError):
            continue
        if pid in excluded_pids:
            continue
        conflicts.append(stripped)
    return conflicts


def stop_tracked_nav_processes(state: dict) -> None:
    for key in ('nav_viewd_pid', 'navd_pid'):
        pid = int(state.get(key) or 0)
        if pid <= 0 or not pid_is_running(pid):
            continue
        process_group_signal(pid, signal.SIGTERM)
        if wait_for_pid_exit(pid, 3.0):
            continue
        process_group_signal(pid, signal.SIGKILL)
        wait_for_pid_exit(pid, 2.0)


def spawn_process(command: list[str], cwd: Path, stdout_log: Path, stderr_log: Path) -> subprocess.Popen:
    stdout_log.parent.mkdir(parents=True, exist_ok=True)
    stderr_log.parent.mkdir(parents=True, exist_ok=True)
    stdout_handle = stdout_log.open('ab')
    stderr_handle = stderr_log.open('ab')
    try:
        return subprocess.Popen(
            command,
            cwd=str(cwd),
            start_new_session=True,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()


def ensure_required_paths() -> None:
    for path in (DEFAULT_NAV_BIN, DEFAULT_NAV_VIEW_BIN, DEFAULT_NAV_CFG, DEFAULT_ESKF_CFG):
        if not path.exists():
            raise RuntimeError(f'missing required path: {path}')


def apply_dvl_policy(enable: bool, state_path: Path) -> dict:
    ensure_required_paths()

    previous_state = read_state(state_path)
    previous_enabled = read_dvl_enable(DEFAULT_NAV_CFG)
    previous_state['dvl_policy_enabled'] = previous_enabled

    navd = None
    nav_viewd = None
    config_changed = False
    try:
        config_changed = write_dvl_enable(DEFAULT_NAV_CFG, enable)
        stop_tracked_nav_processes(previous_state)

        conflicts = detect_untracked_nav_processes(set())
        if conflicts:
            raise RuntimeError(
                'untracked nav processes are already running; refusing to start a parallel nav lane: '
                + '; '.join(conflicts)
            )

        logs_root = state_path.parent / 'child_logs'
        navd = spawn_process(
            [
                str(DEFAULT_NAV_BIN),
                '--config', str(DEFAULT_NAV_CFG),
                '--eskf-config', str(DEFAULT_ESKF_CFG),
            ],
            NAV_CORE_ROOT,
            logs_root / 'uwnav_navd' / 'stdout.log',
            logs_root / 'uwnav_navd' / 'stderr.log',
        )
        time.sleep(0.4)
        navd_rc = navd.poll()
        if navd_rc is not None:
            raise RuntimeError(f'uwnav_navd exited immediately with code={navd_rc}')

        nav_viewd = spawn_process(
            [
                str(DEFAULT_NAV_VIEW_BIN),
                '--nav-state-shm', '/rov_nav_state_v1',
                '--nav-view-shm', '/rovctrl_nav_view_v1',
            ],
            CTRL_ROOT,
            logs_root / 'nav_viewd' / 'stdout.log',
            logs_root / 'nav_viewd' / 'stderr.log',
        )
        time.sleep(0.4)
        nav_viewd_rc = nav_viewd.poll()
        if nav_viewd_rc is not None:
            raise RuntimeError(f'nav_viewd exited immediately with code={nav_viewd_rc}')

        state = build_state(
            dvl_policy_enabled=enable,
            navd_pid=navd.pid,
            nav_viewd_pid=nav_viewd.pid if nav_viewd is not None else 0,
        )
        safe_write_json(state_path, state)
        return state
    except Exception:
        if nav_viewd is not None:
            process_group_signal(nav_viewd.pid, signal.SIGTERM)
            wait_for_pid_exit(nav_viewd.pid, 2.0)
        if navd is not None:
            process_group_signal(navd.pid, signal.SIGTERM)
            wait_for_pid_exit(navd.pid, 2.0)
        if config_changed:
            write_dvl_enable(DEFAULT_NAV_CFG, previous_enabled)
        raise


def cmd_status(args: argparse.Namespace) -> int:
    state = read_state(args.state_file)
    state['dvl_policy_enabled'] = read_dvl_enable(DEFAULT_NAV_CFG)
    state['navd_running'] = pid_is_running(int(state.get('navd_pid') or 0))
    state['nav_viewd_running'] = pid_is_running(int(state.get('nav_viewd_pid') or 0))
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(
            f"dvl_policy_enabled={int(state['dvl_policy_enabled'])} "
            f"navd_pid={int(state.get('navd_pid') or 0)} navd_running={int(state['navd_running'])} "
            f"nav_viewd_pid={int(state.get('nav_viewd_pid') or 0)} nav_viewd_running={int(state['nav_viewd_running'])}"
        )
    return 0


def cmd_apply_dvl(args: argparse.Namespace) -> int:
    enable = bool(int(args.enable))
    try:
        state = apply_dvl_policy(enable, args.state_file)
    except Exception as exc:
        failed_state = build_state(
            dvl_policy_enabled=read_dvl_enable(DEFAULT_NAV_CFG),
            navd_pid=0,
            nav_viewd_pid=0,
            last_error=str(exc),
        )
        safe_write_json(args.state_file, failed_state)
        print(f'[ERR] {exc}', file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(
            f"[OK] dvl_policy_enabled={int(state['dvl_policy_enabled'])} "
            f"navd_pid={state['navd_pid']} nav_viewd_pid={state['nav_viewd_pid']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Manage the standalone nav preview lane and apply the DVL operator policy.',
    )
    parser.add_argument('--state-file', type=Path, default=DEFAULT_STATE_PATH)

    sub = parser.add_subparsers(dest='cmd', required=True)

    status = sub.add_parser('status')
    status.add_argument('--json', action='store_true')
    status.set_defaults(func=cmd_status)

    apply_dvl = sub.add_parser('apply-dvl')
    apply_dvl.add_argument('--enable', required=True, choices=('0', '1'))
    apply_dvl.add_argument('--json', action='store_true')
    apply_dvl.set_defaults(func=cmd_apply_dvl)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == '__main__':
    raise SystemExit(main())
