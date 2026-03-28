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

from tools.supervisor import device_identification, device_profiles, incident_bundle

TELEOP_PRIMARY_LANE_SEQUENCE = [
    'device-check',
    'device-scan',
    'startup-profiles',
    'preflight',
    'start',
    'status',
    'teleop',
    'stop',
    'bundle',
]
MOTION_INFO_FIELD_ALIASES = {
    'roll': ('nav_roll', 'roll'),
    'pitch': ('nav_pitch', 'pitch'),
    'yaw': ('nav_yaw', 'yaw'),
    'velocity': ('vel_norm', 'speed', 'nav_speed', 'dvl_speed'),
    'relative_position': ('nav_x', 'nav_y', 'nav_z', 'rel_x', 'rel_y', 'rel_z'),
    'gyro': ('gyro_x', 'gyro_y', 'gyro_z', 'imu_gyro_x', 'imu_gyro_y', 'imu_gyro_z'),
    'accel': ('accel_x', 'accel_y', 'accel_z', 'imu_accel_x', 'imu_accel_y', 'imu_accel_z'),
}

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
STARTUP_PROFILE_CHOICES = [device_profiles.AUTO_PROFILE] + [item['name'] for item in device_profiles.serialize_profile_catalog()]
SUPERVISOR_PROFILE_CHOICES = ['control_only', 'bench', 'mock']
DEVICE_SCAN_ENABLED_PROFILES = {'control_only', 'bench'}
DEVICE_SCAN_SAMPLE_CHOICES = ['auto', 'off', 'always']


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
    startup_profile_name: str = ''
    startup_profile_source: str = ''
    recommended_startup_profile_name: str = ''
    device_identification_summary: dict = field(default_factory=dict)

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


def build_control_comm_specs() -> List[ProcessSpec]:
    pwm_bin = CTRL_ROOT / 'build' / 'bin' / 'pwm_control_program'
    gcs_bin = CTRL_ROOT / 'build' / 'bin' / 'gcs_server'

    pwm_cfg_dir = CTRL_ROOT / 'pwm_control_program' / 'config'
    pwm_cfg = pwm_cfg_dir / 'pwm_client.yaml'
    alloc_cfg = pwm_cfg_dir / 'alloc.yaml'
    traj_cfg = pwm_cfg_dir / 'trajectory.yaml'
    control_cfg = pwm_cfg_dir / 'control_params.yaml'
    teleop_cfg = pwm_cfg_dir / 'teleop_mixer.yaml'

    return [
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
                # 这里只禁用车载键盘 teleop 输入，保留 gcs_server 遥控链路作为当前主 operator lane。
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

    if name == 'control_only':
        # 当前默认最小可运行路径只启动 control + comm；导航缺失不再被当成 fatal。
        return Profile(
            name='control_only',
            description='Default minimum runtime: start pwm_control_program + gcs_server with navigation disabled by design.',
            process_specs=build_control_comm_specs(),
            gcs_bind_ip='0.0.0.0',
            gcs_bind_port=14550,
        )

    if name == 'bench':
        nav_bin = NAV_CORE_ROOT / 'build' / 'bin' / 'uwnav_navd'
        nav_cfg = NAV_CORE_ROOT / 'config' / 'nav_daemon.yaml'
        eskf_cfg = NAV_CORE_ROOT / 'config' / 'eskf.yaml'

        gw_bin = CTRL_ROOT / 'build' / 'bin' / 'nav_viewd'

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
            *build_control_comm_specs(),
        ]
        return Profile(
            name='bench',
            description='Bench-safe Phase 0 profile with explicit config paths, navigation bring-up, and --pwm-dummy.',
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
    enable_device_scan: bool = False,
    startup_profile_request: str = device_profiles.AUTO_PROFILE,
    device_metadata: Optional[dict] = None,
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
            # bench nav bring-up 仍然要求先把真实设备节点问题前移到 preflight 暴露。
            device_paths = extract_device_paths_from_file(nav_cfg)
            if not device_paths:
                results.append(PreflightResult(True, 'bench_devices', f'no /dev device path found in {nav_cfg}'))
            for device_path in device_paths:
                results.append(check_device_node(device_path, f'bench_device_{device_path.name}'))

    if profile.name in DEVICE_SCAN_ENABLED_PROFILES:
        # control_only 也保留设备扫描与 by-id 提示，但这些结果只影响“导航 readiness 解释”，不再阻塞最小控制链。
        results.append(check_serial_by_id_visibility())

        if enable_device_scan:
            try:
                scan_summary = device_identification.scan_device_inventory(
                    requested_startup_profile=startup_profile_request,
                )
            except Exception as exc:
                results.append(PreflightResult(False, 'device_scan', f'device scan failed ({exc})'))
            else:
                if device_metadata is not None:
                    device_metadata.clear()
                    device_metadata.update(scan_summary)
                results.extend(build_device_scan_preflight_results(profile, scan_summary))

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


def build_empty_device_scan_summary(requested_startup_profile: str) -> dict:
    counts = device_profiles.empty_device_counts()
    rule_catalog = device_identification.serialize_rule_catalog(device_identification.load_rules())
    return {
        'generated_wall_time': wall_time_now(),
        'rules_path': str(device_identification.DEFAULT_RULES_PATH.resolve()),
        'sample_policy': 'off',
        'sample_window_s': 0.0,
        'max_sample_bytes': 0,
        'requested_startup_profile': requested_startup_profile,
        'devices': [],
        'device_counts': counts,
        'device_summary': 'device scan skipped for current runtime profile',
        'rule_catalog': rule_catalog,
        'rule_maturity_summary': device_identification.summarize_rule_catalog(rule_catalog),
        'static_sample_gap_summary': device_identification.summarize_static_sample_gaps(rule_catalog),
        'recommended_bindings': {},
        'ambiguous': False,
        'ambiguous_devices': [],
        'risk_hints': [],
        'recommended_startup_profile': device_profiles.recommend_startup_profile(counts),
        'selected_startup_profile': device_profiles.resolve_startup_profile(requested_startup_profile, counts),
    }


def apply_device_scan_summary(ctx: RunContext, summary: dict) -> None:
    if not summary:
        return
    selected = summary.get('selected_startup_profile') or {}
    recommended = summary.get('recommended_startup_profile') or {}
    ctx.startup_profile_name = str(selected.get('selected') or '')
    ctx.startup_profile_source = str(selected.get('source') or '')
    ctx.recommended_startup_profile_name = str(recommended.get('profile') or '')
    ctx.device_identification_summary = dict(summary)



# 这里保持低风险：只把 device-scan 的存在性结果翻成 operator 友好的低频状态，
# 不在 supervisor 内猜测 runtime driver 级 open/permission 错误。
def build_sensor_inventory_status(summary: dict, capability: dict) -> dict:
    counts = summary.get('device_counts') or device_profiles.empty_device_counts()
    active_level = str(capability.get('level') or 'control_only')

    def _entry(name: str, *, optional: bool, detected_note: str, missing_note: str, required_for: tuple[str, ...]) -> dict:
        value = int(counts.get(name, 0) or 0)
        if value > 0:
            state = 'detected'
            note = detected_note
        else:
            state = 'optional_missing' if optional else 'not_present'
            note = missing_note
        return {
            'count': value,
            'state': state,
            'note': note,
            'required_for_levels': list(required_for),
            'visibility': 'device_scan_inventory',
        }

    imu_missing_note = (
        '未识别到 IMU；当前默认 lane 仍可停在 control_only，但姿态反馈不可用。'
        if active_level == 'control_only'
        else '未识别到 IMU；当前无法形成可直接依赖的姿态反馈。'
    )
    dvl_missing_note = (
        '外接 DVL 未识别；teleop primary lane 可继续，但 relative_nav 不可用。'
        if active_level in {'control_only', 'attitude_feedback'}
        else '外接 DVL 未识别；当前无法形成 relative_nav。'
    )

    return {
        'imu': _entry(
            'imu',
            optional=False,
            detected_note='已识别 IMU；如后续切到 nav preview，可作为 attitude_feedback 升级前提。',
            missing_note=imu_missing_note,
            required_for=('attitude_feedback', 'relative_nav'),
        ),
        'dvl': _entry(
            'dvl',
            optional=True,
            detected_note='已识别外接 DVL；如后续切到 nav preview，可作为 relative_nav 升级前提。',
            missing_note=dvl_missing_note,
            required_for=('relative_nav',),
        ),
        'volt32': _entry(
            'volt32',
            optional=True,
            detected_note='已识别 Volt32；可用于辅助电源观测，但不是 teleop primary lane 启动硬依赖。',
            missing_note='未识别 Volt32；不阻塞 teleop primary lane，可继续用 preflight/device-scan 排查。',
            required_for=(),
        ),
        'usbl': _entry(
            'usbl',
            optional=True,
            detected_note='已识别 USBL 候选；当前仍不进入默认 lane。',
            missing_note='USBL 当前不是默认 lane 必选项。',
            required_for=('full_stack_preview',),
        ),
        'unknown': _entry(
            'unknown',
            optional=True,
            detected_note='存在未识别串口候选；实机验证前应先补 by-id / sample，避免误绑。',
            missing_note='当前没有额外未知串口候选。',
            required_for=(),
        ),
    }


def build_capability_status(profile: Profile, summary: dict) -> dict:
    selected = summary.get('selected_startup_profile') or {}
    startup_profile = str(selected.get('selected') or '')
    device_ready_level = device_profiles.startup_profile_capability_level(startup_profile)
    active_level = device_ready_level if profile.name == 'bench' else 'control_only'
    expected_fields = list(device_profiles.capability_level_motion_fields(active_level))
    teleop_allowed_modes = ['manual', 'failsafe']
    auto_modes_blocked = ['auto', 'nav-dependent closed-loop modes']
    summary_text = device_profiles.capability_level_summary(active_level)
    if profile.name == 'control_only' and device_ready_level != 'control_only':
        summary_text = (
            '当前 runtime 仍固定为 control_only；设备已具备 ' + device_ready_level +
            ' 升级前提，但本轮默认 lane 仍只放行遥控、状态观察、日志和 bundle。'
        )

    return {
        'runtime_profile': profile.name,
        'startup_profile': startup_profile or None,
        'level': active_level,
        'summary': summary_text,
        'device_ready_level': device_ready_level,
        'device_ready_summary': device_profiles.capability_level_summary(device_ready_level),
        'expected_motion_fields': expected_fields,
        'teleop_allowed_modes': teleop_allowed_modes,
        'blocked_modes': auto_modes_blocked,
        'dvl_optional': device_ready_level != 'full_stack_preview',
    }


def build_operator_lane_status(profile: Profile, capability: dict) -> dict:
    return {
        'name': 'teleop_primary',
        'recommended': profile.name == 'control_only',
        'profile': profile.name,
        'sequence': list(TELEOP_PRIMARY_LANE_SEQUENCE),
        'teleop_endpoint': 'UnderWaterRobotGCS TUI',
        'observation_surfaces': ['phase0_supervisor status', 'UnderWaterRobotGCS GUI overview'],
        'navigation_required': capability.get('level') == 'relative_nav' and profile.name == 'bench',
        'teleop_state': 'ready_after_start' if profile.name in {'control_only', 'bench'} else 'not_supported',
    }


def _format_motion_component(row: dict, aliases: tuple[str, ...], *, vector: bool = False) -> str | None:
    values = []
    labels = []
    for key in aliases:
        value = (row.get(key) or '').strip()
        if not value:
            continue
        values.append(value)
        labels.append(key)
    if not values:
        return None
    if vector or len(values) > 1:
        return ', '.join(f'{name}={value}' for name, value in zip(labels, values))
    return values[0]


def _load_latest_csv_row(path: Path) -> dict[str, str] | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    latest: dict[str, str] | None = None
    try:
        with path.open('r', encoding='utf-8', newline='') as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                latest = {str(key): str(value) for key, value in row.items() if key is not None}
    except OSError:
        return None
    return latest


def find_latest_motion_log(manifest: dict) -> tuple[Path | None, str]:
    ctrl_roots = incident_bundle.resolve_ctrl_log_roots(manifest)
    return incident_bundle.select_latest_matching(
        ctrl_roots,
        'control/control_loop_*.csv',
        run_created=incident_bundle.parse_wall_time(manifest.get('created_wall_time')),
    )


def build_motion_info_status(manifest: dict, capability: dict) -> dict:
    level = str(capability.get('level') or 'control_only')
    path, selection_mode = find_latest_motion_log(manifest)
    status = {
        'state': 'unavailable',
        'source': 'control_loop_csv',
        'selection_mode': selection_mode,
        'path': str(path) if path is not None else None,
        'capability_level': level,
        'expected_fields': list(capability.get('expected_motion_fields') or ()),
        'available_fields': [],
        'summary': '当前未发现可读取的 motion snapshot；仍可继续遥控、日志和 bundle。',
        'values': {},
    }
    expected_fields = list(capability.get('expected_motion_fields') or ())
    if not expected_fields:
        status['state'] = 'not_enabled_for_capability'
        status['summary'] = 'control_only 当前不宣称运动反馈；如需姿态/相对运动观察，请补 IMU 或 IMU + DVL。'
        return status

    row = _load_latest_csv_row(path)
    if row is None:
        if level == 'control_only':
            status['summary'] = 'control_only 当前不宣称运动反馈；如需姿态/相对运动观察，请补 IMU 或 IMU + DVL。'
        elif level == 'attitude_feedback':
            status['summary'] = 'IMU 已允许姿态反馈，但当前控制日志里还没有可读取的姿态 snapshot。'
        elif level == 'relative_nav':
            status['summary'] = '相对导航已具备前提，但当前控制日志里还没有可读取的相对运动 snapshot。'
        return status

    values = {}
    available_fields = []
    for field in capability.get('expected_motion_fields') or ():
        aliases = MOTION_INFO_FIELD_ALIASES.get(str(field), ())
        if field in {'gyro', 'accel', 'relative_position'}:
            value = _format_motion_component(row, aliases, vector=True)
        else:
            value = _format_motion_component(row, aliases)
        if value is None:
            continue
        values[str(field)] = value
        available_fields.append(str(field))

    if not values:
        status['state'] = 'present_but_unmapped'
        status['summary'] = '已找到 control_loop 日志，但当前字段映射不足，暂无法提取结构化 motion snapshot。'
        return status

    summary_parts = [f'capability={level}']
    if 'roll' in values and 'pitch' in values and 'yaw' in values:
        summary_parts.append(f"attitude=({values['roll']}, {values['pitch']}, {values['yaw']})")
    if 'velocity' in values:
        summary_parts.append(f"velocity={values['velocity']}")
    if 'relative_position' in values:
        summary_parts.append(f"relative_position={values['relative_position']}")

    status.update({
        'state': 'available',
        'available_fields': available_fields,
        'values': values,
        'summary': '; '.join(summary_parts),
    })
    return status


def build_runtime_observation_summary(profile: Profile, summary: dict, manifest: dict) -> dict:
    capability = build_capability_status(profile, summary)
    sensors = build_sensor_inventory_status(summary, capability)
    operator_lane = build_operator_lane_status(profile, capability)
    motion_info = build_motion_info_status(manifest, capability)
    return {
        'sensor_inventory': sensors,
        'capability': capability,
        'operator_lane': operator_lane,
        'motion_info': motion_info,
    }


def build_device_scan_preflight_results(profile: Profile, summary: dict) -> List[PreflightResult]:
    counts = summary.get('device_counts') or device_profiles.empty_device_counts()
    selected = summary.get('selected_startup_profile') or {}
    recommended = summary.get('recommended_startup_profile') or {}
    bindings = summary.get('recommended_bindings') or {}
    nav_requirement = str(selected.get('navigation_requirement') or '-')
    runtime_hint = str(selected.get('runtime_level_hint') or '-')

    binding_text = 'no trusted binding recommended yet'
    if bindings:
        binding_text = ', '.join(f'{key}={value}' for key, value in sorted(bindings.items()))

    runtime_detail = {
        'control_only': 'mandatory=pwm_control_program,gcs_server optional=uwnav_navd,nav_viewd disabled_by_default=yes',
        'bench': 'mandatory=uwnav_navd,nav_viewd,pwm_control_program,gcs_server optional=- disabled_by_default=no',
    }.get(profile.name, 'mandatory=- optional=- disabled_by_default=-')

    results = [
        PreflightResult(
            True,
            'runtime_level',
            f'profile={profile.name}; {runtime_detail}',
        ),
        PreflightResult(
            True,
            'device_inventory',
            f"{device_profiles.summarize_device_counts(counts)}; {summary.get('device_summary') or '-'}",
        ),
        PreflightResult(
            True,
            'device_recommendations',
            binding_text,
        ),
        PreflightResult(
            True,
            'startup_profile',
            f"requested={summary.get('requested_startup_profile') or device_profiles.AUTO_PROFILE} "
            f"selected={selected.get('selected') or '-'} "
            f"recommended={recommended.get('profile') or '-'} "
            f"launch_mode={selected.get('launch_mode') or '-'} "
            f"nav_requirement={nav_requirement} runtime_hint={runtime_hint} "
            f"device_ready_level={device_profiles.startup_profile_capability_level(selected.get('selected') or '')}",
        ),
    ]

    capability = build_capability_status(profile, summary)
    results.append(
        PreflightResult(
            True,
            'capability_level',
            f"active={capability.get('level')} device_ready={capability.get('device_ready_level')} summary={capability.get('summary')}",
        )
    )

    if summary.get('rule_maturity_summary'):
        results.append(
            PreflightResult(
                True,
                'device_rule_maturity',
                str(summary.get('rule_maturity_summary') or '-'),
            )
        )

    if summary.get('static_sample_gap_summary'):
        results.append(
            PreflightResult(
                True,
                'device_static_sample_gaps',
                str(summary.get('static_sample_gap_summary') or '-'),
            )
        )

    if summary.get('ambiguous'):
        ambiguity_detail = ', '.join(summary.get('ambiguous_devices') or []) or 'ambiguous serial candidates detected'
        if profile.name == 'control_only':
            results.append(
                PreflightResult(
                    True,
                    'device_binding_ambiguity',
                    ambiguity_detail + '; control_only lane will keep navigation disabled and continue with control + comm only',
                )
            )
        else:
            results.append(
                PreflightResult(
                    False,
                    'device_binding_ambiguity',
                    ambiguity_detail,
                )
            )

    if selected.get('errors'):
        requirement_detail = '; '.join(selected.get('errors') or [])
        if profile.name == 'control_only':
            results.append(
                PreflightResult(
                    True,
                    'startup_profile_requirements',
                    requirement_detail + '; control_only lane treats startup_profile as navigation readiness only and still allows start',
                )
            )
        else:
            results.append(
                PreflightResult(
                    False,
                    'startup_profile_requirements',
                    requirement_detail,
                )
            )

    if profile.name == 'bench':
        gate_ok = selected.get('launch_mode') == 'bench_safe_smoke'
        gate_detail = (
            f"selected startup profile={selected.get('selected') or '-'} launch_mode={selected.get('launch_mode') or '-'}; "
            + ('bench-safe nav lane allowed' if gate_ok else 'keep to preflight / sensor tools only')
        )
        results.append(PreflightResult(gate_ok, 'startup_profile_gate', gate_detail))
    elif profile.name == 'control_only':
        results.append(
            PreflightResult(
                True,
                'startup_profile_gate',
                f"runtime profile=control_only selected startup profile={selected.get('selected') or '-'}; "
                'navigation is optional here, so missing/ambiguous nav devices do not block start; AUTO and nav-dependent bring-up remain disabled',
            )
        )

    notes = list(selected.get('warnings') or []) + list(summary.get('risk_hints') or [])
    if notes:
        results.append(PreflightResult(True, 'device_scan_risks', '; '.join(notes)))

    return results


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

    observation = build_runtime_observation_summary(ctx.profile, ctx.device_identification_summary, {
        'created_wall_time': ctx.created_wall_time,
        'processes': process_entries,
    })

    return {
        'run_id': ctx.run_id,
        'profile': ctx.profile.name,
        'profile_description': ctx.profile.description,
        'startup_profile': ctx.startup_profile_name or None,
        'startup_profile_source': ctx.startup_profile_source or None,
        'recommended_startup_profile': ctx.recommended_startup_profile_name or None,
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
        'device_identification': ctx.device_identification_summary or None,
        'sensor_inventory': observation['sensor_inventory'],
        'capability': observation['capability'],
        'operator_lane': observation['operator_lane'],
        'motion_info': observation['motion_info'],
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
    process_entries = [runtime.to_status_dict() for runtime in ctx.processes]
    observation = build_runtime_observation_summary(ctx.profile, ctx.device_identification_summary, {
        'created_wall_time': ctx.created_wall_time,
        'processes': process_entries,
    })
    return {
        'run_id': ctx.run_id,
        'profile': ctx.profile.name,
        'startup_profile': ctx.startup_profile_name or None,
        'startup_profile_source': ctx.startup_profile_source or None,
        'recommended_startup_profile': ctx.recommended_startup_profile_name or None,
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
        'device_identification': ctx.device_identification_summary or None,
        'sensor_inventory': observation['sensor_inventory'],
        'capability': observation['capability'],
        'operator_lane': observation['operator_lane'],
        'motion_info': observation['motion_info'],
        'processes': process_entries,
    }


def write_process_status(ctx: RunContext) -> None:
    safe_write_json(ctx.status_path, build_process_status(ctx))


def write_last_fault_summary(ctx: RunContext) -> None:
    details = dict(ctx.last_fault_details)
    lines = [
        f'run_id={ctx.run_id}',
        f'profile={ctx.profile.name}',
        f'updated_wall_time={ctx.last_fault_wall_time or wall_time_now()}',
        f'supervisor_state={ctx.supervisor_state}',
        f'event={ctx.last_fault_event}',
        f'process_name={ctx.last_fault_process_name or ""}',
        f'message={ctx.last_fault_message}',
    ]

    if ctx.startup_profile_name:
        lines.append(f'startup_profile={ctx.startup_profile_name}')
    if ctx.startup_profile_source:
        lines.append(f'startup_profile_source={ctx.startup_profile_source}')
    if ctx.recommended_startup_profile_name:
        lines.append(f'recommended_startup_profile={ctx.recommended_startup_profile_name}')
    observation = build_runtime_observation_summary(ctx.profile, ctx.device_identification_summary, {
        'created_wall_time': ctx.created_wall_time,
        'processes': [
            {
                'name': runtime.spec.name,
                'cwd': str(runtime.spec.cwd),
                'required_paths': [str(path) for path in runtime.spec.required_paths],
            }
            for runtime in ctx.processes
        ],
    })
    lines.append('operator_lane=teleop_primary')
    lines.append(f"teleop_lane_sequence={' -> '.join(TELEOP_PRIMARY_LANE_SEQUENCE)}")
    lines.append(f"teleop_path_state={observation['operator_lane'].get('teleop_state')}")
    lines.append(f"capability_level={observation['capability'].get('level')}")
    lines.append(f"capability_summary={observation['capability'].get('summary')}")
    lines.append(f"motion_info_state={observation['motion_info'].get('state')}")
    lines.append(f"motion_info_source={observation['motion_info'].get('source')}")
    lines.append(f"motion_info_summary={observation['motion_info'].get('summary')}")
    if ctx.device_identification_summary:
        device_counts = ctx.device_identification_summary.get('device_counts') or device_profiles.empty_device_counts()
        lines.append(f"device_counts={device_profiles.summarize_device_counts(device_counts)}")
        lines.append(f"sensor_inventory_json={json.dumps(observation['sensor_inventory'], ensure_ascii=False, sort_keys=True)}")
        bindings = ctx.device_identification_summary.get('recommended_bindings') or {}
        if bindings:
            lines.append(f"recommended_bindings={json.dumps(bindings, ensure_ascii=False, sort_keys=True)}")
        compact_devices = [
            {
                'device_type': item.get('device_type'),
                'current_path': item.get('current_path'),
                'confidence': item.get('confidence', {}).get('score'),
                'ambiguous': item.get('ambiguous'),
            }
            for item in ctx.device_identification_summary.get('devices', [])
        ]
        if compact_devices:
            lines.append(f"identified_devices_json={json.dumps(compact_devices, ensure_ascii=False, sort_keys=True)}")

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

    device_metadata: dict = {}
    results = run_preflight_checks(
        profile,
        run_root,
        skip_port_check=args.skip_port_check,
        ignore_run_dir=run_dir,
        enable_device_scan=profile.name in DEVICE_SCAN_ENABLED_PROFILES,
        startup_profile_request=args.startup_profile,
        device_metadata=device_metadata,
    )
    if device_metadata:
        apply_device_scan_summary(ctx, device_metadata)
        write_manifest(ctx)
        write_process_status(ctx)
        write_last_fault_summary(ctx)
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
        enable_device_scan=profile.name in DEVICE_SCAN_ENABLED_PROFILES,
        startup_profile_request=args.startup_profile,
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
        '--startup-profile', args.startup_profile,
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
    manifest_path = run_dir / 'run_manifest.json'
    manifest = load_json(manifest_path) if manifest_path.exists() else {
        'created_wall_time': data.get('updated_wall_time'),
        'processes': [
            {
                'name': item.get('name'),
                'cwd': item.get('cwd'),
                'required_paths': [],
            }
            for item in data.get('processes', [])
        ],
    }
    observation = build_runtime_observation_summary(
        build_profile(str(data.get('profile') or 'control_only')) if str(data.get('profile') or 'control_only') in SUPERVISOR_PROFILE_CHOICES else build_profile('control_only'),
        data.get('device_identification') or {},
        manifest,
    )
    data['sensor_inventory'] = observation['sensor_inventory']
    data['capability'] = observation['capability']
    data['operator_lane'] = observation['operator_lane']
    data['motion_info'] = observation['motion_info']

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    header = (
        f"run_id={data.get('run_id')} profile={data.get('profile')} "
        f"state={data.get('supervisor_state')} child_output={data.get('child_output_mode')}"
    )
    if data.get('startup_profile'):
        header += f" startup_profile={data.get('startup_profile')}"
    if data.get('recommended_startup_profile'):
        header += f" recommended_startup_profile={data.get('recommended_startup_profile')}"
    print(header)
    capability = data.get('capability') or {}
    operator_lane = data.get('operator_lane') or {}
    motion_info = data.get('motion_info') or {}
    sensor_inventory = data.get('sensor_inventory') or {}
    print(
        f"capability={capability.get('level')} summary={capability.get('summary')}"
    )
    print(
        f"operator_lane={operator_lane.get('name')} teleop_state={operator_lane.get('teleop_state')} sequence={' -> '.join(operator_lane.get('sequence') or [])}"
    )
    print(
        f"motion_info={motion_info.get('state')} source={motion_info.get('source')} summary={motion_info.get('summary')}"
    )
    print(
        'sensor_inventory=' + ' '.join(
            f"{name}={sensor_inventory.get(name, {}).get('state')}"
            for name in ('imu', 'dvl', 'volt32', 'usbl', 'unknown')
            if isinstance(sensor_inventory.get(name), dict)
        )
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


def cmd_device_scan(args: argparse.Namespace) -> int:
    try:
        summary = device_identification.scan_device_inventory(
            dev_root=args.dev_root.resolve(),
            sys_root=args.sys_root.resolve(),
            rules_path=args.rules_path.resolve() if args.rules_path is not None else None,
            sample_policy=args.sample_policy,
            sample_window_s=args.sample_window_s,
            max_sample_bytes=max(1, int(args.max_sample_bytes)),
            requested_startup_profile=args.startup_profile,
        )
    except Exception as exc:
        print(f'[ERR] device scan failed: {exc}')
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        device_identification.print_table(summary)
    return 0


def cmd_startup_profiles(args: argparse.Namespace) -> int:
    catalog = device_profiles.serialize_profile_catalog()
    if args.json:
        print(json.dumps(catalog, ensure_ascii=False, indent=2))
        return 0

    for item in catalog:
        required = ','.join(item['required_devices']) or '-'
        print(
            f"{item['name']}: launch_mode={item['launch_mode']} nav={item['navigation_requirement']} runtime_hint={item['runtime_level_hint']} capability={item['capability_level']} implemented={str(item['implemented']).lower()} required={required}"
        )
    return 0


def cmd_bundle(args: argparse.Namespace) -> int:
    run_dir = resolve_target_run_dir(args.run_root.resolve(), args.run_dir.resolve() if args.run_dir is not None else None)
    if run_dir is None:
        print('[ERR] no supervisor run found')
        return 1

    bundle_dir = args.bundle_dir.resolve() if args.bundle_dir is not None else None
    try:
        summary = incident_bundle.export_run_bundle(run_dir, bundle_dir=bundle_dir)
    except incident_bundle.IncidentBundleError as exc:
        print(f'[ERR] {exc}')
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"[INFO] bundle_dir={summary['bundle_dir']}")
        print(f"[INFO] bundle_export_ok={int(bool(summary.get('bundle_export_ok', True)))}")
        print(f"[INFO] bundle_status={summary['bundle_status']} (artifact_completeness)")
        print(f"[INFO] run_stage={summary['run_stage']}")
        if summary['bundle_incomplete']:
            if summary['required_ok']:
                missing = ', '.join(summary['missing_optional_keys'])
                print(f'[WARN] bundle export succeeded, but optional artifacts are missing: {missing or "-"}')
            else:
                missing = ', '.join(summary['missing_required_keys'])
                print(f'[WARN] bundle export succeeded, but required artifacts are missing: {missing or "-"}')
        print('[INFO] first look:')
        for item in summary['start_here']:
            print(f'  {item}')
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Phase 0 thin supervisor / launcher prototype.')
    sub = parser.add_subparsers(dest='command', required=True)

    preflight = sub.add_parser('preflight', help='Run minimal preflight checks only.')
    preflight.add_argument('--profile', default='control_only', choices=SUPERVISOR_PROFILE_CHOICES)
    preflight.add_argument('--run-root', type=Path, default=DEFAULT_RUN_ROOT)
    preflight.add_argument('--skip-port-check', action='store_true')
    preflight.add_argument('--startup-profile', default=device_profiles.AUTO_PROFILE, choices=STARTUP_PROFILE_CHOICES)
    preflight.set_defaults(func=cmd_preflight)

    start = sub.add_parser('start', help='Start supervisor in foreground or detached mode.')
    start.add_argument('--profile', default='control_only', choices=SUPERVISOR_PROFILE_CHOICES)
    start.add_argument('--run-root', type=Path, default=DEFAULT_RUN_ROOT)
    start.add_argument('--run-id')
    start.add_argument('--detach', action='store_true')
    start.add_argument('--start-settle-s', type=float, default=0.5)
    start.add_argument('--poll-interval-s', type=float, default=0.5)
    start.add_argument('--stop-timeout-s', type=float, default=8.0)
    start.add_argument('--fault-tail-lines', type=int, default=DEFAULT_FAULT_TAIL_LINES)
    start.add_argument('--skip-port-check', action='store_true')
    start.add_argument('--startup-profile', default=device_profiles.AUTO_PROFILE, choices=STARTUP_PROFILE_CHOICES)
    start.add_argument('--child-output', choices=[OUTPUT_INHERIT, OUTPUT_CAPTURE, OUTPUT_QUIET])
    start.add_argument('--quiet-children', action='store_true', help='Compatibility alias for --child-output quiet')
    start.set_defaults(func=cmd_start)

    internal = sub.add_parser('_run')
    internal.add_argument('--profile', default='control_only', choices=SUPERVISOR_PROFILE_CHOICES)
    internal.add_argument('--run-root', type=Path, default=DEFAULT_RUN_ROOT)
    internal.add_argument('--run-dir', type=Path, required=True)
    internal.add_argument('--run-id')
    internal.add_argument('--start-settle-s', type=float, default=0.5)
    internal.add_argument('--poll-interval-s', type=float, default=0.5)
    internal.add_argument('--stop-timeout-s', type=float, default=8.0)
    internal.add_argument('--fault-tail-lines', type=int, default=DEFAULT_FAULT_TAIL_LINES)
    internal.add_argument('--skip-port-check', action='store_true')
    internal.add_argument('--startup-profile', default=device_profiles.AUTO_PROFILE, choices=STARTUP_PROFILE_CHOICES)
    internal.add_argument('--child-output', choices=[OUTPUT_INHERIT, OUTPUT_CAPTURE, OUTPUT_QUIET], default=OUTPUT_CAPTURE)
    internal.add_argument('--quiet-children', action='store_true', help='Compatibility alias for --child-output quiet')
    internal.set_defaults(func=run_supervisor)

    device_scan = sub.add_parser('device-scan', help='Inspect serial devices and recommend a startup profile.')
    device_scan.add_argument('--dev-root', type=Path, default=Path('/dev'))
    device_scan.add_argument('--sys-root', type=Path, default=Path('/sys/class/tty'))
    device_scan.add_argument('--rules-path', type=Path, default=device_identification.DEFAULT_RULES_PATH)
    device_scan.add_argument('--sample-policy', choices=DEVICE_SCAN_SAMPLE_CHOICES, default=device_identification.DEFAULT_SAMPLE_POLICY)
    device_scan.add_argument('--sample-window-s', type=float, default=device_identification.DEFAULT_SAMPLE_WINDOW_S)
    device_scan.add_argument('--max-sample-bytes', type=int, default=device_identification.DEFAULT_MAX_SAMPLE_BYTES)
    device_scan.add_argument('--startup-profile', default=device_profiles.AUTO_PROFILE, choices=STARTUP_PROFILE_CHOICES)
    device_scan.add_argument('--json', action='store_true')
    device_scan.set_defaults(func=cmd_device_scan)

    profile_matrix = sub.add_parser('startup-profiles', help='Show the startup profile capability matrix.')
    profile_matrix.add_argument('--json', action='store_true')
    profile_matrix.set_defaults(func=cmd_startup_profiles)

    status = sub.add_parser('status', help='Show current process status file.')
    status.add_argument('--run-root', type=Path, default=DEFAULT_RUN_ROOT)
    status.add_argument('--run-dir', type=Path)
    status.add_argument('--json', action='store_true')
    status.set_defaults(func=cmd_status)



    bundle = sub.add_parser('bundle', help='Export a minimal incident bundle from the latest or specified run.')
    bundle.add_argument('--run-root', type=Path, default=DEFAULT_RUN_ROOT)
    bundle.add_argument('--run-dir', type=Path)
    bundle.add_argument('--bundle-dir', type=Path)
    bundle.add_argument('--json', action='store_true')
    bundle.set_defaults(func=cmd_bundle)

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
