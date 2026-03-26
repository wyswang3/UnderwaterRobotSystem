#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent
NAV_CORE_ROOT = WORKSPACE_ROOT / 'Underwater-robot-navigation' / 'nav_core'
CTRL_ROOT = WORKSPACE_ROOT / 'OrangePi_STM32_for_ROV'
DEFAULT_RUN_ROOT = REPO_ROOT / 'reports' / 'supervisor_runs'

STATE_NOT_STARTED = 'not_started'
STATE_STARTING = 'starting'
STATE_RUNNING = 'running'
STATE_RETRYING = 'retrying'
STATE_STOPPED = 'stopped'
STATE_FAILED = 'failed'
STATE_STOPPING = 'stopping'

OUTPUT_INHERIT = 'inherit'
OUTPUT_CAPTURE = 'capture'
OUTPUT_QUIET = 'quiet'
DEFAULT_FAULT_TAIL_LINES = 20

EVENT_HEADER = [
    'mono_ns',
    'wall_time',
    'component',
    'event',
    'level',
    'run_id',
    'message',
    'process_name',
    'action',
    'result',
    'pid',
    'exit_code',
    'restart_count',
]

DEVICE_PORT_RE = re.compile(r'^\s*port:\s*"(?P<path>/dev/[^"]+)"\s*$')


class SupervisorError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessSpec:
    name: str
    role: str
    cwd: Path
    command: List[str]
    required_paths: List[Path]


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    process_specs: List[ProcessSpec]
    gcs_bind_ip: Optional[str] = None
    gcs_bind_port: Optional[int] = None


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    title: str
    detail: str


@dataclass
class ProcessRuntime:
    spec: ProcessSpec
    state: str = STATE_NOT_STARTED
    pid: Optional[int] = None
    start_wall_time: str = ''
    stop_wall_time: str = ''
    exit_code: Optional[int] = None
    restart_count: int = 0
    last_failure_reason: str = ''
    stdout_log_path: Optional[Path] = None
    stderr_log_path: Optional[Path] = None
    stdout_tail: str = ''
    stderr_tail: str = ''
    process: Optional[subprocess.Popen] = field(default=None, repr=False)
    stdout_handle: Optional[BinaryIO] = field(default=None, repr=False)
    stderr_handle: Optional[BinaryIO] = field(default=None, repr=False)

    def to_status_dict(self) -> dict:
        return {
            'name': self.spec.name,
            'role': self.spec.role,
            'state': self.state,
            'pid': self.pid,
            'start_wall_time': self.start_wall_time or None,
            'stop_wall_time': self.stop_wall_time or None,
            'exit_code': self.exit_code,
            'restart_count': self.restart_count,
            'last_failure_reason': self.last_failure_reason,
            'cwd': str(self.spec.cwd),
            'command': list(self.spec.command),
            'log_files': {
                'stdout': str(self.stdout_log_path) if self.stdout_log_path is not None else None,
                'stderr': str(self.stderr_log_path) if self.stderr_log_path is not None else None,
            },
            'output_excerpt': {
                'stdout_tail': self.stdout_tail or None,
                'stderr_tail': self.stderr_tail or None,
            },
        }


@dataclass
class RunContext:
    profile: Profile
    run_id: str
    run_root: Path
    run_dir: Path
    child_output_mode: str
    poll_interval_s: float
    stop_timeout_s: float
    fault_tail_lines: int
    processes: List[ProcessRuntime]
    supervisor_state: str = STATE_STARTING
    mono_start_ns: int = field(default_factory=time.monotonic_ns)
    created_wall_time: str = field(default_factory=lambda: wall_time_now())
    last_fault_event: str = 'none'
    last_fault_message: str = 'no fault recorded'
    last_fault_wall_time: str = ''
    last_fault_process_name: str = ''
    last_fault_details: dict = field(default_factory=dict)

    @property
    def supervisor_pid(self) -> int:
        return os.getpid()

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / 'run_manifest.json'

    @property
    def status_path(self) -> Path:
        return self.run_dir / 'process_status.json'

    @property
    def fault_path(self) -> Path:
        return self.run_dir / 'last_fault_summary.txt'

    @property
    def events_path(self) -> Path:
        return self.run_dir / 'supervisor_events.csv'

    @property
    def child_logs_dir(self) -> Path:
        return self.run_dir / 'child_logs'


_STOP_REQUESTED = False


def wall_time_now() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def safe_write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + '.tmp')
    tmp_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp_path.replace(path)


def safe_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + '.tmp')
    tmp_path.write_text(text, encoding='utf-8')
    tmp_path.replace(path)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def build_run_id() -> str:
    now = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f'{now}_{os.getpid()}'


def build_run_dir(run_root: Path, run_id: str) -> Path:
    date_dir = datetime.now().strftime('%Y-%m-%d')
    return run_root / date_dir / run_id


def normalize_child_output_mode(child_output: Optional[str], quiet_children: bool, *, default_mode: str) -> str:
    if child_output:
        return child_output
    if quiet_children:
        return OUTPUT_QUIET
    return default_mode


def read_text_tail(path: Optional[Path], max_lines: int, *, max_bytes: int = 32 * 1024) -> str:
    if path is None or max_lines <= 0 or not path.exists():
        return ''

    try:
        with path.open('rb') as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes), os.SEEK_SET)
            data = handle.read()
    except OSError:
        return ''

    text = data.decode('utf-8', errors='replace')
    lines = text.splitlines()
    return '\n'.join(lines[-max_lines:]).strip()


def discover_latest_run_dir(run_root: Path) -> Optional[Path]:
    if not run_root.exists():
        return None
    manifests = sorted(run_root.rglob('run_manifest.json'), key=lambda p: p.stat().st_mtime)
    if not manifests:
        return None
    return manifests[-1].parent


def resolve_target_run_dir(run_root: Path, run_dir: Optional[Path]) -> Optional[Path]:
    if run_dir is not None:
        return run_dir
    return discover_latest_run_dir(run_root)


def build_profile(name: str) -> Profile:
    if name == 'mock':
        sleep_bin = Path('/bin/sleep')
        specs = [
            ProcessSpec('uwnav_navd', 'nav', REPO_ROOT, [str(sleep_bin), '3600'], [sleep_bin]),
            ProcessSpec('nav_viewd', 'bridge', REPO_ROOT, [str(sleep_bin), '3600'], [sleep_bin]),
            ProcessSpec('pwm_control_program', 'control', REPO_ROOT, [str(sleep_bin), '3600'], [sleep_bin]),
            ProcessSpec('gcs_server', 'comm', REPO_ROOT, [str(sleep_bin), '3600'], [sleep_bin]),
        ]
        return Profile(
            name='mock',
            description='Mock profile for lifecycle validation without touching authority binaries.',
            process_specs=specs,
        )

    if name == 'bench':
        nav_bin = NAV_CORE_ROOT / 'build' / 'bin' / 'uwnav_navd'
        nav_cfg = NAV_CORE_ROOT / 'config' / 'nav_daemon.yaml'
        eskf_cfg = NAV_CORE_ROOT / 'config' / 'eskf.yaml'

        gw_bin = CTRL_ROOT / 'build' / 'bin' / 'nav_viewd'
        gcs_bin = CTRL_ROOT / 'build' / 'bin' / 'gcs_server'
        pwm_bin = CTRL_ROOT / 'build' / 'bin' / 'pwm_control_program'

        pwm_cfg_dir = CTRL_ROOT / 'pwm_control_program' / 'config'
        pwm_cfg = pwm_cfg_dir / 'pwm_client.yaml'
        alloc_cfg = pwm_cfg_dir / 'alloc.yaml'
        traj_cfg = pwm_cfg_dir / 'trajectory.yaml'
        control_cfg = pwm_cfg_dir / 'control_params.yaml'
        teleop_cfg = pwm_cfg_dir / 'teleop_mixer.yaml'

        specs = [
            ProcessSpec(
                name='uwnav_navd',
                role='nav',
                cwd=NAV_CORE_ROOT,
                command=[
                    str(nav_bin),
                    '--config', str(nav_cfg),
                    '--eskf-config', str(eskf_cfg),
                ],
                required_paths=[nav_bin, nav_cfg, eskf_cfg],
            ),
            ProcessSpec(
                name='nav_viewd',
                role='bridge',
                cwd=CTRL_ROOT,
                command=[
                    str(gw_bin),
                    '--nav-state-shm', '/rov_nav_state_v1',
                    '--nav-view-shm', '/rovctrl_nav_view_v1',
                ],
                required_paths=[gw_bin],
            ),
            ProcessSpec(
                name='pwm_control_program',
                role='control',
                cwd=CTRL_ROOT,
                command=[
                    str(pwm_bin),
                    '--config', str(pwm_cfg),
                    '--alloc-config', str(alloc_cfg),
                    '--traj-config', str(traj_cfg),
                    '--control-config', str(control_cfg),
                    '--teleop-mixer-config', str(teleop_cfg),
                    '--no-teleop',
                    '--pwm-dummy',
                ],
                required_paths=[pwm_bin, pwm_cfg, alloc_cfg, traj_cfg, control_cfg, teleop_cfg],
            ),
            ProcessSpec(
                name='gcs_server',
                role='comm',
                cwd=CTRL_ROOT,
                command=[
                    str(gcs_bin),
                    '--ip', '0.0.0.0',
                    '--port', '14550',
                    '--intent-shm', '/rovctrl_gcs_intent_v1',
                ],
                required_paths=[gcs_bin],
            ),
        ]
        return Profile(
            name='bench',
            description='Bench-safe Phase 0 profile with explicit config paths and --pwm-dummy.',
            process_specs=specs,
            gcs_bind_ip='0.0.0.0',
            gcs_bind_port=14550,
        )

    raise SupervisorError(f'unsupported profile: {name}')


def check_run_root(run_root: Path) -> PreflightResult:
    try:
        run_root.mkdir(parents=True, exist_ok=True)
        probe = run_root / '.supervisor_write_probe'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink()
    except OSError as exc:
        return PreflightResult(False, 'run_root', f'cannot write run root {run_root} ({exc})')
    return PreflightResult(True, 'run_root', f'run root ready: {run_root}')


def check_directory_access(path: Path, title: str, *, writable: bool = False) -> PreflightResult:
    if not path.exists():
        return PreflightResult(False, title, f'missing directory: {path}')
    if not path.is_dir():
        return PreflightResult(False, title, f'not a directory: {path}')

    mode = os.R_OK | os.X_OK
    if writable:
        mode |= os.W_OK
    if not os.access(path, mode):
        suffix = 'read/write/search' if writable else 'read/search'
        return PreflightResult(False, title, f'directory is not {suffix}-ready: {path}')
    return PreflightResult(True, title, str(path))


def check_python_runtime() -> PreflightResult:
    version = sys.version.split()[0]
    if sys.version_info < (3, 10):
        return PreflightResult(False, 'python', f'Python {version} is too old; require >= 3.10')
    return PreflightResult(True, 'python', f'Python {version}')


def check_file_readable(path: Path, title: str) -> PreflightResult:
    if not path.exists():
        return PreflightResult(False, title, f'missing required file: {path}')
    if not path.is_file():
        return PreflightResult(False, title, f'not a regular file: {path}')
    if not os.access(path, os.R_OK):
        return PreflightResult(False, title, f'file is not readable: {path}')
    return PreflightResult(True, title, str(path))


def extract_device_paths_from_text(text: str) -> List[str]:
    devices: List[str] = []
    seen = set()
    for line in text.splitlines():
        match = DEVICE_PORT_RE.match(line)
        if match is None:
            continue
        device_path = match.group('path')
        if device_path in seen:
            continue
        seen.add(device_path)
        devices.append(device_path)
    return devices


def extract_device_paths_from_file(path: Path) -> List[Path]:
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return []
    return [Path(item) for item in extract_device_paths_from_text(text)]


def check_device_node(path: Path, title: str) -> PreflightResult:
    if not path.exists():
        return PreflightResult(False, title, f'missing device node: {path}')
    if not os.access(path, os.R_OK | os.W_OK):
        return PreflightResult(False, title, f'device node is not read/write ready: {path}')
    return PreflightResult(True, title, str(path))


def check_serial_by_id_visibility() -> PreflightResult:
    by_id_dir = Path('/dev/serial/by-id')
    if not by_id_dir.exists():
        return PreflightResult(True, 'serial_by_id', '/dev/serial/by-id not present; fixed tty paths will be used')
    if not by_id_dir.is_dir():
        return PreflightResult(False, 'serial_by_id', f'not a directory: {by_id_dir}')
    if not os.access(by_id_dir, os.R_OK | os.X_OK):
        return PreflightResult(False, 'serial_by_id', f'directory is not readable: {by_id_dir}')
    entry_count = sum(1 for _ in by_id_dir.iterdir())
    return PreflightResult(True, 'serial_by_id', f'{by_id_dir} visible with {entry_count} entries')


def check_existing_active_run(run_root: Path, *, ignore_run_dir: Optional[Path] = None) -> Optional[PreflightResult]:
    latest_run = discover_latest_run_dir(run_root)
    if latest_run is None:
        return None
    if ignore_run_dir is not None and latest_run.resolve() == ignore_run_dir.resolve():
        return None
    manifest_path = latest_run / 'run_manifest.json'
    if not manifest_path.exists():
        return None
    try:
        manifest = load_json(manifest_path)
    except Exception:
        return None
    pid = int(manifest.get('supervisor_pid') or 0)
    run_id = manifest.get('run_id', '<unknown>')
    if pid > 0 and pid_is_running(pid):
        return PreflightResult(False, 'active_run', f'run_id={run_id} supervisor_pid={pid} still active under {latest_run}')
    return None


def check_bind_port(ip: str, port: int) -> PreflightResult:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((ip, port))
    except OSError as exc:
        return PreflightResult(False, 'gcs_bind', f'cannot bind {ip}:{port} ({exc})')
    finally:
        sock.close()
    return PreflightResult(True, 'gcs_bind', f'{ip}:{port} is available for gcs_server')


def run_preflight_checks(
    profile: Profile,
    run_root: Path,
    *,
    skip_port_check: bool = False,
    ignore_run_dir: Optional[Path] = None,
) -> List[PreflightResult]:
    results: List[PreflightResult] = [
        check_python_runtime(),
        check_run_root(run_root),
        check_directory_access(Path('/dev/shm'), 'shm_runtime', writable=True),
    ]

    active = check_existing_active_run(run_root, ignore_run_dir=ignore_run_dir)
    if active is not None:
        results.append(active)

    for spec in profile.process_specs:
        results.append(check_directory_access(spec.cwd, f'{spec.name}_cwd'))
        if not spec.required_paths:
            continue

        binary = spec.required_paths[0]
        if not binary.exists():
            results.append(PreflightResult(False, f'{spec.name}_binary', f'missing binary: {binary}'))
        elif not binary.is_file():
            results.append(PreflightResult(False, f'{spec.name}_binary', f'not a regular file: {binary}'))
        elif not os.access(binary, os.X_OK):
            results.append(PreflightResult(False, f'{spec.name}_binary', f'not executable: {binary}'))
        else:
            results.append(PreflightResult(True, f'{spec.name}_binary', str(binary)))

        for dep in spec.required_paths[1:]:
            title = f'{spec.name}_{dep.name}'
            results.append(check_file_readable(dep, title))

    if profile.name == 'bench':
        nav_cfg = next(
            (
                dep
                for spec in profile.process_specs
                if spec.name == 'uwnav_navd'
                for dep in spec.required_paths[1:]
                if dep.name == 'nav_daemon.yaml'
            ),
            None,
        )
        if nav_cfg is not None:
            # Phase 0 先把“设备路径是否可见”前移到 preflight，避免把问题留给子进程启动后才暴露。
            device_paths = extract_device_paths_from_file(nav_cfg)
            if not device_paths:
                results.append(PreflightResult(True, 'bench_devices', f'no /dev device path found in {nav_cfg}'))
            for device_path in device_paths:
                results.append(check_device_node(device_path, f'bench_device_{device_path.name}'))

        # by-id 缺失先记为提示，不阻塞当前固定 tty 路径的 bench 配置。
        results.append(check_serial_by_id_visibility())

    if profile.gcs_bind_ip and profile.gcs_bind_port and not skip_port_check:
        results.append(check_bind_port(profile.gcs_bind_ip, profile.gcs_bind_port))

    return results


def print_preflight(profile: Profile, results: Sequence[PreflightResult]) -> None:
    print('')
    print('============================================')
    print(f' Phase0 Supervisor Preflight ({profile.name})')
    print('============================================')
    print(f'[INFO] profile={profile.description}')
    print('')
    for item in results:
        prefix = '[ OK ]' if item.ok else '[ERR]'
        print(f'{prefix} {item.title}: {item.detail}')


def preflight_failed(results: Sequence[PreflightResult]) -> bool:
    return any(not item.ok for item in results)


def append_event_row(path: Path, row: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open('a', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        if write_header:
            writer.writerow(EVENT_HEADER)
        writer.writerow(row)


def build_manifest(ctx: RunContext) -> dict:
    process_entries = []
    for runtime in ctx.processes:
        process_entries.append(
            {
                'name': runtime.spec.name,
                'role': runtime.spec.role,
                'cwd': str(runtime.spec.cwd),
                'command': list(runtime.spec.command),
                'required_paths': [str(path) for path in runtime.spec.required_paths],
                'log_files': {
                    'stdout': str(runtime.stdout_log_path) if runtime.stdout_log_path is not None else None,
                    'stderr': str(runtime.stderr_log_path) if runtime.stderr_log_path is not None else None,
                },
            }
        )

    return {
        'run_id': ctx.run_id,
        'profile': ctx.profile.name,
        'profile_description': ctx.profile.description,
        'created_wall_time': ctx.created_wall_time,
        'updated_wall_time': wall_time_now(),
        'mono_start_ns': ctx.mono_start_ns,
        'supervisor_pid': ctx.supervisor_pid,
        'supervisor_state': ctx.supervisor_state,
        'child_output_mode': ctx.child_output_mode,
        'fault_tail_lines': ctx.fault_tail_lines,
        'run_root': str(ctx.run_root),
        'run_dir': str(ctx.run_dir),
        'child_logs_dir': str(ctx.child_logs_dir),
        'run_files': {
            'run_manifest': str(ctx.manifest_path),
            'process_status': str(ctx.status_path),
            'last_fault_summary': str(ctx.fault_path),
            'supervisor_events': str(ctx.events_path),
        },
        'last_fault_event': ctx.last_fault_event,
        'last_fault_process_name': ctx.last_fault_process_name or None,
        'process_order': [runtime.spec.name for runtime in ctx.processes],
        'shutdown_order': [runtime.spec.name for runtime in reversed(ctx.processes)],
        'processes': process_entries,
    }


def write_manifest(ctx: RunContext) -> None:
    safe_write_json(ctx.manifest_path, build_manifest(ctx))


def build_process_status(ctx: RunContext) -> dict:
    return {
        'run_id': ctx.run_id,
        'profile': ctx.profile.name,
        'supervisor_pid': ctx.supervisor_pid,
        'supervisor_state': ctx.supervisor_state,
        'child_output_mode': ctx.child_output_mode,
        'fault_tail_lines': ctx.fault_tail_lines,
        'child_logs_dir': str(ctx.child_logs_dir),
        'updated_wall_time': wall_time_now(),
        'last_fault_event': ctx.last_fault_event,
        'last_fault_message': ctx.last_fault_message,
        'last_fault_process_name': ctx.last_fault_process_name or None,
        'last_fault_details': ctx.last_fault_details,
        'processes': [runtime.to_status_dict() for runtime in ctx.processes],
    }


def write_process_status(ctx: RunContext) -> None:
    safe_write_json(ctx.status_path, build_process_status(ctx))


def write_last_fault_summary(ctx: RunContext) -> None:
    details = dict(ctx.last_fault_details)
    lines = [
        f'run_id={ctx.run_id}',
        f'updated_wall_time={ctx.last_fault_wall_time or wall_time_now()}',
        f'supervisor_state={ctx.supervisor_state}',
        f'event={ctx.last_fault_event}',
        f'process_name={ctx.last_fault_process_name or ""}',
        f'message={ctx.last_fault_message}',
    ]

    stdout_log = details.get('stdout_log')
    stderr_log = details.get('stderr_log')
    if stdout_log:
        lines.append(f'stdout_log={stdout_log}')
    if stderr_log:
        lines.append(f'stderr_log={stderr_log}')
    if details:
        lines.append(f'detail_json={json.dumps(details, ensure_ascii=False, sort_keys=True)}')
    lines.append('')

    stdout_tail = details.get('stdout_tail')
    stderr_tail = details.get('stderr_tail')
    if stdout_tail:
        lines.extend(['[stdout_tail]', stdout_tail, ''])
    if stderr_tail:
        lines.extend(['[stderr_tail]', stderr_tail, ''])

    safe_write_text(ctx.fault_path, '\n'.join(lines))


def update_last_fault(
    ctx: RunContext,
    event: str,
    message: str,
    *,
    process_name: str = '',
    details: Optional[dict] = None,
) -> None:
    ctx.last_fault_event = event
    ctx.last_fault_message = message
    ctx.last_fault_wall_time = wall_time_now()
    ctx.last_fault_process_name = process_name
    ctx.last_fault_details = dict(details or {})
    write_last_fault_summary(ctx)
    write_process_status(ctx)
    write_manifest(ctx)


def log_event(
    ctx: RunContext,
    event: str,
    level: str,
    message: str,
    *,
    process_name: str = '',
    action: str = '',
    result: str = '',
    pid: Optional[int] = None,
    exit_code: Optional[int] = None,
    restart_count: int = 0,
) -> None:
    row = [
        str(time.monotonic_ns()),
        wall_time_now(),
        'supervisor',
        event,
        level,
        ctx.run_id,
        message,
        process_name,
        action,
        result,
        '' if pid is None else str(pid),
        '' if exit_code is None else str(exit_code),
        str(restart_count),
    ]
    append_event_row(ctx.events_path, row)
    if ctx.child_output_mode != OUTPUT_QUIET:
        prefix = level.upper().ljust(5)
        print(f'[{prefix}] {event}: {message}')


def close_process_output_handles(runtime: ProcessRuntime) -> None:
    for handle in (runtime.stdout_handle, runtime.stderr_handle):
        if handle is None:
            continue
        try:
            handle.flush()
        except OSError:
            pass
        try:
            handle.close()
        except OSError:
            pass
    runtime.stdout_handle = None
    runtime.stderr_handle = None


def snapshot_process_output(runtime: ProcessRuntime, tail_lines: int) -> dict:
    for handle in (runtime.stdout_handle, runtime.stderr_handle):
        if handle is not None:
            try:
                handle.flush()
            except OSError:
                pass

    runtime.stdout_tail = read_text_tail(runtime.stdout_log_path, tail_lines)
    runtime.stderr_tail = read_text_tail(runtime.stderr_log_path, tail_lines)

    details = {}
    if runtime.stdout_log_path is not None:
        details['stdout_log'] = str(runtime.stdout_log_path)
    if runtime.stderr_log_path is not None:
        details['stderr_log'] = str(runtime.stderr_log_path)
    if runtime.stdout_tail:
        details['stdout_tail'] = runtime.stdout_tail
    if runtime.stderr_tail:
        details['stderr_tail'] = runtime.stderr_tail
    return details


def install_signal_handlers() -> None:
    def _handle_signal(signum: int, _frame) -> None:
        del signum
        global _STOP_REQUESTED
        _STOP_REQUESTED = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)


def spawn_process(ctx: RunContext, runtime: ProcessRuntime) -> subprocess.Popen:
    close_process_output_handles(runtime)
    runtime.stdout_tail = ''
    runtime.stderr_tail = ''

    stdout = None
    stderr = None
    if ctx.child_output_mode == OUTPUT_QUIET:
        stdout = subprocess.DEVNULL
        stderr = subprocess.DEVNULL
    elif ctx.child_output_mode == OUTPUT_CAPTURE:
        process_dir = ctx.child_logs_dir / runtime.spec.name
        process_dir.mkdir(parents=True, exist_ok=True)
        runtime.stdout_log_path = process_dir / 'stdout.log'
        runtime.stderr_log_path = process_dir / 'stderr.log'
        runtime.stdout_handle = runtime.stdout_log_path.open('ab')
        runtime.stderr_handle = runtime.stderr_log_path.open('ab')
        stdout = runtime.stdout_handle
        stderr = runtime.stderr_handle
    else:
        runtime.stdout_log_path = None
        runtime.stderr_log_path = None

    return subprocess.Popen(
        list(runtime.spec.command),
        cwd=str(runtime.spec.cwd),
        start_new_session=True,
        stdout=stdout,
        stderr=stderr,
    )


def note_process_exit(ctx: RunContext, runtime: ProcessRuntime, exit_code: int, *, expected_stop: bool) -> None:
    runtime.exit_code = exit_code
    runtime.stop_wall_time = wall_time_now()

    output_details = {}
    if not expected_stop and exit_code != 0:
        output_details = snapshot_process_output(runtime, ctx.fault_tail_lines)
    close_process_output_handles(runtime)

    if expected_stop or exit_code == 0:
        runtime.state = STATE_STOPPED
        message = f'{runtime.spec.name} exited with code={exit_code}'
        log_event(
            ctx,
            'process_stopped',
            'info',
            message,
            process_name=runtime.spec.name,
            action='stop' if expected_stop else 'monitor',
            result='ok',
            pid=runtime.pid,
            exit_code=exit_code,
            restart_count=runtime.restart_count,
        )
    else:
        runtime.state = STATE_FAILED
        runtime.last_failure_reason = f'exit_code={exit_code}'
        message = f'{runtime.spec.name} exited unexpectedly with code={exit_code}'
        log_event(
            ctx,
            'process_stopped',
            'error',
            message,
            process_name=runtime.spec.name,
            action='monitor',
            result='failed',
            pid=runtime.pid,
            exit_code=exit_code,
            restart_count=runtime.restart_count,
        )
        update_last_fault(
            ctx,
            'process_stopped',
            message,
            process_name=runtime.spec.name,
            details=output_details,
        )

    write_process_status(ctx)
    write_manifest(ctx)


def process_group_signal(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        return


def wait_for_pid_exit(pid: int, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not pid_is_running(pid):
            return True
        time.sleep(0.1)
    return not pid_is_running(pid)


def shutdown_process(ctx: RunContext, runtime: ProcessRuntime, timeout_s: float) -> None:
    if runtime.pid is None:
        return

    # 如果子进程已经退出，直接按当前退出码收口。
    if runtime.process is not None:
        polled = runtime.process.poll()
        if polled is not None and runtime.state in {STATE_RUNNING, STATE_STARTING, STATE_STOPPING}:
            note_process_exit(ctx, runtime, polled, expected_stop=True)
            return

    if not pid_is_running(runtime.pid):
        if runtime.state in {STATE_RUNNING, STATE_STARTING, STATE_STOPPING}:
            note_process_exit(ctx, runtime, 0, expected_stop=True)
        return

    runtime.state = STATE_STOPPING
    write_process_status(ctx)
    write_manifest(ctx)

    log_event(
        ctx,
        'process_stop_requested',
        'info',
        f'sending SIGTERM to {runtime.spec.name}',
        process_name=runtime.spec.name,
        action='stop',
        result='pending',
        pid=runtime.pid,
        restart_count=runtime.restart_count,
    )
    process_group_signal(runtime.pid, signal.SIGTERM)

    if runtime.process is not None:
        try:
            exit_code = runtime.process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            exit_code = None
        else:
            note_process_exit(ctx, runtime, exit_code, expected_stop=True)
            return
    else:
        if wait_for_pid_exit(runtime.pid, timeout_s):
            note_process_exit(ctx, runtime, 0, expected_stop=True)
            return

    log_event(
        ctx,
        'process_killed',
        'warn',
        f'{runtime.spec.name} did not exit after SIGTERM; sending SIGKILL',
        process_name=runtime.spec.name,
        action='stop',
        result='retrying',
        pid=runtime.pid,
        restart_count=runtime.restart_count,
    )
    process_group_signal(runtime.pid, signal.SIGKILL)

    if runtime.process is not None:
        try:
            exit_code = runtime.process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            exit_code = None
        else:
            note_process_exit(ctx, runtime, exit_code, expected_stop=True)
            return
    else:
        if wait_for_pid_exit(runtime.pid, 2.0):
            note_process_exit(ctx, runtime, -signal.SIGKILL, expected_stop=True)
            return

    runtime.state = STATE_FAILED
    runtime.last_failure_reason = 'stop_timeout'
    write_process_status(ctx)
    write_manifest(ctx)
    update_last_fault(
        ctx,
        'process_killed',
        f'{runtime.spec.name} could not be stopped cleanly',
        process_name=runtime.spec.name,
        details=snapshot_process_output(runtime, ctx.fault_tail_lines),
    )


def init_run_context(
    profile: Profile,
    run_root: Path,
    run_dir: Path,
    child_output_mode: str,
    poll_interval_s: float,
    stop_timeout_s: float,
    fault_tail_lines: int,
) -> RunContext:
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_dir.name
    processes = [ProcessRuntime(spec=spec) for spec in profile.process_specs]
    if child_output_mode == OUTPUT_CAPTURE:
        for runtime in processes:
            process_dir = run_dir / 'child_logs' / runtime.spec.name
            process_dir.mkdir(parents=True, exist_ok=True)
            runtime.stdout_log_path = process_dir / 'stdout.log'
            runtime.stderr_log_path = process_dir / 'stderr.log'
            runtime.stdout_log_path.touch(exist_ok=True)
            runtime.stderr_log_path.touch(exist_ok=True)
    return RunContext(
        profile=profile,
        run_id=run_id,
        run_root=run_root,
        run_dir=run_dir,
        child_output_mode=child_output_mode,
        poll_interval_s=poll_interval_s,
        stop_timeout_s=stop_timeout_s,
        fault_tail_lines=max(0, int(fault_tail_lines)),
        processes=processes,
    )


def start_process_sequence(ctx: RunContext, start_settle_s: float) -> None:
    for runtime in ctx.processes:
        runtime.state = STATE_STARTING
        write_process_status(ctx)
        write_manifest(ctx)
        try:
            proc = spawn_process(ctx, runtime)
        except OSError as exc:
            runtime.state = STATE_FAILED
            runtime.last_failure_reason = str(exc)
            close_process_output_handles(runtime)
            log_event(
                ctx,
                'process_start_failed',
                'error',
                f'{runtime.spec.name} start failed: {exc}',
                process_name=runtime.spec.name,
                action='start',
                result='failed',
            )
            update_last_fault(
                ctx,
                'process_start_failed',
                f'{runtime.spec.name} start failed: {exc}',
                process_name=runtime.spec.name,
                details={
                    'cwd': str(runtime.spec.cwd),
                    'command': list(runtime.spec.command),
                    'stdout_log': str(runtime.stdout_log_path) if runtime.stdout_log_path is not None else '',
                    'stderr_log': str(runtime.stderr_log_path) if runtime.stderr_log_path is not None else '',
                },
            )
            continue

        runtime.process = proc
        runtime.pid = proc.pid
        runtime.start_wall_time = wall_time_now()
        runtime.state = STATE_RUNNING
        log_event(
            ctx,
            'process_started',
            'info',
            f'{runtime.spec.name} started',
            process_name=runtime.spec.name,
            action='start',
            result='ok',
            pid=runtime.pid,
            restart_count=runtime.restart_count,
        )
        write_process_status(ctx)
        write_manifest(ctx)

        if start_settle_s > 0.0:
            time.sleep(start_settle_s)
            polled = proc.poll()
            if polled is not None:
                note_process_exit(ctx, runtime, polled, expected_stop=False)


def monitor_loop(ctx: RunContext) -> None:
    while True:
        any_running = False
        for runtime in ctx.processes:
            if runtime.process is None:
                continue
            polled = runtime.process.poll()
            if polled is None:
                if runtime.state == STATE_RUNNING:
                    any_running = True
                continue
            if runtime.state in {STATE_RUNNING, STATE_STARTING}:
                note_process_exit(ctx, runtime, polled, expected_stop=False)

        if _STOP_REQUESTED:
            return

        if not any_running:
            return

        time.sleep(ctx.poll_interval_s)


def finalize_run(ctx: RunContext) -> int:
    if ctx.last_fault_event == 'none':
        ctx.last_fault_event = 'supervisor_stopped'
        ctx.last_fault_message = 'stopped without recorded fault'
        ctx.last_fault_wall_time = wall_time_now()
        write_last_fault_summary(ctx)

    ctx.supervisor_state = STATE_FAILED if any(proc.state == STATE_FAILED for proc in ctx.processes) else STATE_STOPPED
    write_process_status(ctx)
    write_manifest(ctx)
    log_event(
        ctx,
        'supervisor_stopped',
        'info' if ctx.supervisor_state == STATE_STOPPED else 'error',
        f'supervisor finished with state={ctx.supervisor_state}',
        action='stop',
        result=ctx.supervisor_state,
        pid=ctx.supervisor_pid,
    )
    return 0 if ctx.supervisor_state == STATE_STOPPED else 1


def run_supervisor(args: argparse.Namespace) -> int:
    global _STOP_REQUESTED
    _STOP_REQUESTED = False

    profile = build_profile(args.profile)
    run_root = args.run_root.resolve()
    run_dir = args.run_dir.resolve() if args.run_dir is not None else build_run_dir(run_root, args.run_id or build_run_id())
    child_output_mode = normalize_child_output_mode(
        getattr(args, 'child_output', None),
        getattr(args, 'quiet_children', False),
        default_mode=OUTPUT_CAPTURE,
    )
    ctx = init_run_context(
        profile,
        run_root,
        run_dir,
        child_output_mode,
        args.poll_interval_s,
        args.stop_timeout_s,
        args.fault_tail_lines,
    )

    install_signal_handlers()

    write_manifest(ctx)
    write_process_status(ctx)
    write_last_fault_summary(ctx)
    log_event(
        ctx,
        'supervisor_started',
        'info',
        f'phase0 supervisor starting with profile={profile.name} child_output={ctx.child_output_mode}',
        action='start',
        result='ok',
        pid=ctx.supervisor_pid,
    )

    results = run_preflight_checks(
        profile,
        run_root,
        skip_port_check=args.skip_port_check,
        ignore_run_dir=run_dir,
    )
    for item in results:
        event = 'preflight_passed' if item.ok else 'preflight_failed'
        level = 'info' if item.ok else 'error'
        log_event(ctx, event, level, f'{item.title}: {item.detail}', action='check', result='ok' if item.ok else 'failed')

    if preflight_failed(results):
        ctx.supervisor_state = STATE_FAILED
        failed_items = [
            {'title': item.title, 'detail': item.detail}
            for item in results
            if not item.ok
        ]
        failure_titles = ', '.join(item['title'] for item in failed_items)
        update_last_fault(
            ctx,
            'preflight_failed',
            f'preflight failed: {failure_titles}',
            details={'failed_checks': failed_items},
        )
        write_process_status(ctx)
        write_manifest(ctx)
        return 1

    ctx.supervisor_state = STATE_RUNNING
    write_process_status(ctx)
    write_manifest(ctx)

    start_process_sequence(ctx, args.start_settle_s)
    monitor_loop(ctx)

    if _STOP_REQUESTED:
        ctx.supervisor_state = STATE_STOPPING
        write_process_status(ctx)
        write_manifest(ctx)
        log_event(
            ctx,
            'supervisor_shutdown_requested',
            'info',
            'received stop signal; shutting down in reverse order',
            action='stop',
            result='pending',
            pid=ctx.supervisor_pid,
        )
        for runtime in reversed(ctx.processes):
            shutdown_process(ctx, runtime, ctx.stop_timeout_s)

    return finalize_run(ctx)


def cmd_preflight(args: argparse.Namespace) -> int:
    profile = build_profile(args.profile)
    run_root = args.run_root.resolve()
    results = run_preflight_checks(
        profile,
        run_root,
        skip_port_check=args.skip_port_check,
        ignore_run_dir=None,
    )
    print_preflight(profile, results)
    return 1 if preflight_failed(results) else 0


def cmd_start(args: argparse.Namespace) -> int:
    run_root = args.run_root.resolve()
    run_id = args.run_id or build_run_id()
    run_dir = build_run_dir(run_root, run_id)

    child_output_mode = normalize_child_output_mode(
        getattr(args, 'child_output', None),
        getattr(args, 'quiet_children', False),
        default_mode=OUTPUT_CAPTURE if args.detach else OUTPUT_INHERIT,
    )
    if args.detach and child_output_mode == OUTPUT_INHERIT:
        print('[WARN] detached mode cannot inherit child stdout/stderr; using capture instead')
        child_output_mode = OUTPUT_CAPTURE
    args.child_output = child_output_mode

    if not args.detach:
        args.run_dir = run_dir
        return run_supervisor(args)

    child_cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        '_run',
        '--profile', args.profile,
        '--run-root', str(run_root),
        '--run-dir', str(run_dir),
        '--start-settle-s', str(args.start_settle_s),
        '--poll-interval-s', str(args.poll_interval_s),
        '--stop-timeout-s', str(args.stop_timeout_s),
        '--fault-tail-lines', str(args.fault_tail_lines),
        '--child-output', child_output_mode,
    ]
    if args.skip_port_check:
        child_cmd.append('--skip-port-check')

    proc = subprocess.Popen(
        child_cmd,
        cwd=str(REPO_ROOT),
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + 3.0
    manifest_path = run_dir / 'run_manifest.json'
    while time.time() < deadline:
        if manifest_path.exists():
            break
        if proc.poll() is not None:
            break
        time.sleep(0.1)

    print(f'[INFO] detached supervisor pid={proc.pid} run_id={run_id}')
    print(f'[INFO] run_dir={run_dir}')
    print(f'[INFO] child_output={child_output_mode}')
    return 0 if proc.poll() is None else int(proc.returncode or 1)


def cmd_status(args: argparse.Namespace) -> int:
    run_dir = resolve_target_run_dir(args.run_root.resolve(), args.run_dir.resolve() if args.run_dir is not None else None)
    if run_dir is None:
        print('[ERR] no supervisor run found')
        return 1

    status_path = run_dir / 'process_status.json'
    if not status_path.exists():
        print(f'[ERR] missing process status: {status_path}')
        return 1

    data = load_json(status_path)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(
        f"run_id={data.get('run_id')} profile={data.get('profile')} "
        f"state={data.get('supervisor_state')} child_output={data.get('child_output_mode')}"
    )
    for proc in data.get('processes', []):
        log_files = proc.get('log_files') or {}
        extras = []
        if log_files.get('stdout'):
            extras.append(f"stdout_log={log_files['stdout']}")
        if log_files.get('stderr'):
            extras.append(f"stderr_log={log_files['stderr']}")
        suffix = '' if not extras else ' ' + ' '.join(extras)
        print(
            f"- {proc['name']}: state={proc['state']} pid={proc['pid']} exit_code={proc['exit_code']}{suffix}"
        )
    return 0


def fallback_stop(run_dir: Path, timeout_s: float) -> int:
    status_path = run_dir / 'process_status.json'
    manifest_path = run_dir / 'run_manifest.json'
    fault_path = run_dir / 'last_fault_summary.txt'
    events_path = run_dir / 'supervisor_events.csv'

    if not status_path.exists():
        print(f'[ERR] missing process status: {status_path}')
        return 1

    status = load_json(status_path)
    processes = list(status.get('processes', []))

    def _append(event: str, level: str, message: str, *, process_name: str = '', pid: Optional[int] = None, exit_code: Optional[int] = None, result: str = '') -> None:
        append_event_row(
            events_path,
            [
                str(time.monotonic_ns()),
                wall_time_now(),
                'supervisor',
                event,
                level,
                str(status.get('run_id', '<unknown>')),
                message,
                process_name,
                'stop',
                result,
                '' if pid is None else str(pid),
                '' if exit_code is None else str(exit_code),
                '0',
            ],
        )

    for proc in reversed(processes):
        pid = int(proc.get('pid') or 0)
        if pid <= 0 or not pid_is_running(pid):
            if proc.get('state') in {STATE_RUNNING, STATE_STARTING, STATE_STOPPING}:
                proc['state'] = STATE_STOPPED
                proc['stop_wall_time'] = wall_time_now()
                proc['exit_code'] = 0
            continue

        _append('process_stop_requested', 'info', f'sending SIGTERM to {proc["name"]} without live supervisor', process_name=proc['name'], pid=pid, result='pending')
        process_group_signal(pid, signal.SIGTERM)
        if wait_for_pid_exit(pid, timeout_s):
            proc['state'] = STATE_STOPPED
            proc['stop_wall_time'] = wall_time_now()
            proc['exit_code'] = 0
            _append('process_stopped', 'info', f'{proc["name"]} stopped without live supervisor', process_name=proc['name'], pid=pid, exit_code=0, result='ok')
            continue

        process_group_signal(pid, signal.SIGKILL)
        if wait_for_pid_exit(pid, 2.0):
            proc['state'] = STATE_STOPPED
            proc['stop_wall_time'] = wall_time_now()
            proc['exit_code'] = -signal.SIGKILL
            _append('process_killed', 'warn', f'{proc["name"]} killed without live supervisor', process_name=proc['name'], pid=pid, exit_code=-signal.SIGKILL, result='ok')
            continue

        proc['state'] = STATE_FAILED
        proc['stop_wall_time'] = wall_time_now()
        proc['exit_code'] = None
        proc['last_failure_reason'] = 'stop_timeout'
        _append('process_killed', 'error', f'{proc["name"]} could not be stopped', process_name=proc['name'], pid=pid, result='failed')

    status['supervisor_state'] = STATE_FAILED if any(proc.get('state') == STATE_FAILED for proc in processes) else STATE_STOPPED
    status['updated_wall_time'] = wall_time_now()
    status['last_fault_event'] = 'supervisor_stop_fallback'
    status['last_fault_message'] = 'fallback stop executed without live supervisor'
    status['processes'] = processes
    safe_write_json(status_path, status)

    if manifest_path.exists():
        manifest = load_json(manifest_path)
        manifest['supervisor_state'] = status['supervisor_state']
        manifest['updated_wall_time'] = wall_time_now()
        safe_write_json(manifest_path, manifest)

    safe_write_text(
        fault_path,
        '\n'.join(
            [
                f"run_id={status.get('run_id', '<unknown>')}",
                f'updated_wall_time={wall_time_now()}',
                f"supervisor_state={status['supervisor_state']}",
                'event=supervisor_stop_fallback',
                'message=fallback stop executed without live supervisor',
                '',
            ]
        ),
    )
    print(f'[INFO] fallback stop completed for run_dir={run_dir}')
    return 0 if status['supervisor_state'] == STATE_STOPPED else 1


def cmd_stop(args: argparse.Namespace) -> int:
    run_dir = resolve_target_run_dir(args.run_root.resolve(), args.run_dir.resolve() if args.run_dir is not None else None)
    if run_dir is None:
        print('[ERR] no supervisor run found')
        return 1

    manifest_path = run_dir / 'run_manifest.json'
    if not manifest_path.exists():
        print(f'[ERR] missing manifest: {manifest_path}')
        return 1

    manifest = load_json(manifest_path)
    supervisor_pid = int(manifest.get('supervisor_pid') or 0)
    if supervisor_pid > 0 and pid_is_running(supervisor_pid):
        os.kill(supervisor_pid, signal.SIGTERM)
        deadline = time.time() + args.timeout_s
        while time.time() < deadline:
            if not pid_is_running(supervisor_pid):
                print(f'[INFO] supervisor pid={supervisor_pid} stopped')
                return 0
            time.sleep(0.2)
        print(f'[WARN] supervisor pid={supervisor_pid} did not exit in time; using fallback stop')

    return fallback_stop(run_dir, args.timeout_s)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Phase 0 thin supervisor / launcher prototype.')
    sub = parser.add_subparsers(dest='command', required=True)

    preflight = sub.add_parser('preflight', help='Run minimal preflight checks only.')
    preflight.add_argument('--profile', default='bench', choices=['bench', 'mock'])
    preflight.add_argument('--run-root', type=Path, default=DEFAULT_RUN_ROOT)
    preflight.add_argument('--skip-port-check', action='store_true')
    preflight.set_defaults(func=cmd_preflight)

    start = sub.add_parser('start', help='Start supervisor in foreground or detached mode.')
    start.add_argument('--profile', default='bench', choices=['bench', 'mock'])
    start.add_argument('--run-root', type=Path, default=DEFAULT_RUN_ROOT)
    start.add_argument('--run-id')
    start.add_argument('--detach', action='store_true')
    start.add_argument('--start-settle-s', type=float, default=0.5)
    start.add_argument('--poll-interval-s', type=float, default=0.5)
    start.add_argument('--stop-timeout-s', type=float, default=8.0)
    start.add_argument('--fault-tail-lines', type=int, default=DEFAULT_FAULT_TAIL_LINES)
    start.add_argument('--skip-port-check', action='store_true')
    start.add_argument('--child-output', choices=[OUTPUT_INHERIT, OUTPUT_CAPTURE, OUTPUT_QUIET])
    start.add_argument('--quiet-children', action='store_true', help='Compatibility alias for --child-output quiet')
    start.set_defaults(func=cmd_start)

    internal = sub.add_parser('_run')
    internal.add_argument('--profile', default='bench', choices=['bench', 'mock'])
    internal.add_argument('--run-root', type=Path, default=DEFAULT_RUN_ROOT)
    internal.add_argument('--run-dir', type=Path, required=True)
    internal.add_argument('--run-id')
    internal.add_argument('--start-settle-s', type=float, default=0.5)
    internal.add_argument('--poll-interval-s', type=float, default=0.5)
    internal.add_argument('--stop-timeout-s', type=float, default=8.0)
    internal.add_argument('--fault-tail-lines', type=int, default=DEFAULT_FAULT_TAIL_LINES)
    internal.add_argument('--skip-port-check', action='store_true')
    internal.add_argument('--child-output', choices=[OUTPUT_INHERIT, OUTPUT_CAPTURE, OUTPUT_QUIET], default=OUTPUT_CAPTURE)
    internal.add_argument('--quiet-children', action='store_true', help='Compatibility alias for --child-output quiet')
    internal.set_defaults(func=run_supervisor)

    status = sub.add_parser('status', help='Show current process status file.')
    status.add_argument('--run-root', type=Path, default=DEFAULT_RUN_ROOT)
    status.add_argument('--run-dir', type=Path)
    status.add_argument('--json', action='store_true')
    status.set_defaults(func=cmd_status)

    stop = sub.add_parser('stop', help='Stop the latest or specified run.')
    stop.add_argument('--run-root', type=Path, default=DEFAULT_RUN_ROOT)
    stop.add_argument('--run-dir', type=Path)
    stop.add_argument('--timeout-s', type=float, default=10.0)
    stop.set_defaults(func=cmd_stop)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == '__main__':
    raise SystemExit(main())
