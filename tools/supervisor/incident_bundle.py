#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent
NAV_CORE_ROOT = WORKSPACE_ROOT / 'Underwater-robot-navigation' / 'nav_core'
MERGE_TOOL = NAV_CORE_ROOT / 'tools' / 'merge_robot_timeline.py'


class IncidentBundleError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactRecord:
    key: str
    group: str
    required: bool
    status: str
    source_path: Optional[str]
    bundle_path: Optional[str]
    selection_mode: str
    detail: str
    size_bytes: Optional[int]

    def to_dict(self) -> dict:
        return {
            'key': self.key,
            'group': self.group,
            'required': self.required,
            'status': self.status,
            'source_path': self.source_path,
            'bundle_path': self.bundle_path,
            'selection_mode': self.selection_mode,
            'detail': self.detail,
            'size_bytes': self.size_bytes,
        }


def wall_time_now() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


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


def parse_wall_time(raw: object) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def default_bundle_dir(run_dir: Path) -> Path:
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return run_dir / 'bundle' / stamp


def process_map(manifest: dict) -> dict[str, dict]:
    return {
        str(item.get('name')): item
        for item in manifest.get('processes', [])
        if isinstance(item, dict) and item.get('name')
    }


def first_existing_with_mode(candidates: Sequence[tuple[Path, str]]) -> tuple[Optional[Path], str]:
    for path, mode in candidates:
        if path.exists() and path.is_file():
            return path, mode
    return None, 'missing_exact_path'


def strip_simple_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


# nav 日志目录不走 supervisor run_root，而是沿用 nav_daemon.yaml 的 logging.base_dir。
# 这里显式解析配置，是为了让 Phase 1 bundle 复用已有日志真源，避免引入第二套目录约定。
def parse_nav_logging_config(path: Path) -> dict[str, object]:
    text = path.read_text(encoding='utf-8')
    in_logging = False
    logging_indent: Optional[int] = None
    base_dir: Optional[str] = None
    split_by_date = True

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        indent = len(line) - len(line.lstrip(' '))
        if stripped == 'logging:':
            in_logging = True
            logging_indent = indent
            continue
        if not in_logging:
            continue
        if logging_indent is not None and indent <= logging_indent:
            break
        if stripped.startswith('base_dir:'):
            value = stripped.split(':', 1)[1]
            base_dir = strip_simple_quotes(value)
        elif stripped.startswith('split_by_date:'):
            value = stripped.split(':', 1)[1].strip().lower()
            split_by_date = value in {'true', '1', 'yes', 'on'}

    if not base_dir:
        raise IncidentBundleError(f'nav logging.base_dir missing in {path}')
    return {
        'base_dir': base_dir,
        'split_by_date': split_by_date,
    }


def resolve_nav_log_dir(manifest: dict) -> tuple[Optional[Path], str]:
    processes = process_map(manifest)
    nav_entry = processes.get('uwnav_navd')
    if not nav_entry:
        return None, 'uwnav_navd missing from manifest'

    nav_cfg_path: Optional[Path] = None
    for raw in nav_entry.get('required_paths', []) or []:
        path = Path(str(raw))
        if path.name == 'nav_daemon.yaml':
            nav_cfg_path = path
            break
    if nav_cfg_path is None or not nav_cfg_path.exists():
        return None, 'nav_daemon.yaml missing from manifest required_paths'

    cfg = parse_nav_logging_config(nav_cfg_path)
    base_dir = Path(str(cfg['base_dir']))
    run_created = parse_wall_time(manifest.get('created_wall_time'))
    if bool(cfg['split_by_date']):
        run_date = run_created.date().isoformat() if run_created is not None else datetime.now().date().isoformat()
        base_dir = base_dir / run_date
    return base_dir / 'nav', f'nav_daemon.yaml logging.base_dir ({nav_cfg_path})'


def resolve_ctrl_log_roots(manifest: dict) -> list[tuple[Path, str]]:
    processes = process_map(manifest)
    roots: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for name in ('nav_viewd', 'pwm_control_program', 'gcs_server'):
        entry = processes.get(name)
        if not entry:
            continue
        cwd_raw = entry.get('cwd')
        if not cwd_raw:
            continue
        cwd = Path(str(cwd_raw))
        for path, mode in (
            (cwd / 'logs', 'cwd_logs'),
            (cwd / 'build' / 'logs', 'build_logs'),
        ):
            if path in seen:
                continue
            seen.add(path)
            roots.append((path, mode))
    return roots


# control / telemetry 日志可能会保留历史文件；这里只拿 run start 之后的最新文件，
# 这样 mock / safe smoke 导出的 bundle 不会误吸进旧轮次数据。
def select_latest_matching(
    roots: Sequence[tuple[Path, str]],
    pattern: str,
    *,
    run_created: Optional[datetime],
) -> tuple[Optional[Path], str]:
    candidates: list[tuple[Path, str, float]] = []
    for root, mode in roots:
        if not root.exists() or not root.is_dir():
            continue
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            candidates.append((path, mode, mtime))

    if not candidates:
        return None, 'no_match'

    if run_created is not None:
        threshold = run_created.timestamp() - 5.0
        recent = [item for item in candidates if item[2] >= threshold]
        if recent:
            path, mode, _ = max(recent, key=lambda item: item[2])
            return path, f'latest_after_run_start:{mode}'
        return None, 'no_match_after_run_start'

    path, mode, _ = max(candidates, key=lambda item: item[2])
    return path, f'latest_without_run_start:{mode}'


def copy_artifact(
    bundle_dir: Path,
    *,
    key: str,
    group: str,
    required: bool,
    source_path: Optional[Path],
    bundle_relpath: Path,
    selection_mode: str,
    detail: str,
) -> ArtifactRecord:
    if source_path is None:
        return ArtifactRecord(
            key=key,
            group=group,
            required=required,
            status='missing',
            source_path=None,
            bundle_path=None,
            selection_mode=selection_mode,
            detail=detail,
            size_bytes=None,
        )

    if not source_path.exists() or not source_path.is_file():
        return ArtifactRecord(
            key=key,
            group=group,
            required=required,
            status='missing',
            source_path=str(source_path),
            bundle_path=None,
            selection_mode=selection_mode,
            detail=detail,
            size_bytes=None,
        )

    dest = bundle_dir / bundle_relpath
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source_path, dest)
    except OSError as exc:
        raise IncidentBundleError(f'copy failed for {source_path}: {exc}') from exc

    size_bytes: Optional[int]
    try:
        size_bytes = source_path.stat().st_size
    except OSError:
        size_bytes = None

    return ArtifactRecord(
        key=key,
        group=group,
        required=required,
        status='copied',
        source_path=str(source_path),
        bundle_path=str(bundle_relpath),
        selection_mode=selection_mode,
        detail=detail,
        size_bytes=size_bytes,
    )


def build_text_summary(summary: dict) -> str:
    lines = [
        f"run_id={summary['run_id']}",
        f"profile={summary['profile']}",
        f"run_stage={summary['run_stage']}",
        f"last_fault_event={summary['last_fault_event'] or '-'}",
        f"bundle_exported_wall_time={summary['bundle_exported_wall_time']}",
        f"bundle_dir={summary['bundle_dir']}",
        f"bundle_export_ok={int(bool(summary.get('bundle_export_ok', True)))}",
        f"bundle_status={summary['bundle_status']}",
        f"bundle_status_meaning={summary.get('bundle_status_meaning', 'artifact_completeness')}",
        f"bundle_incomplete={int(bool(summary['bundle_incomplete']))}",
        f"required_ok={int(bool(summary['required_ok']))}",
        f"missing_required={','.join(summary['missing_required_keys']) if summary['missing_required_keys'] else '-'}",
        f"missing_optional={','.join(summary['missing_optional_keys']) if summary['missing_optional_keys'] else '-'}",
        '',
        '[start_here]',
    ]
    for item in summary['start_here']:
        lines.append(item)

    merge = summary['merge_robot_timeline']
    lines.extend([
        '',
        '[merge_robot_timeline]',
        f"ready={int(bool(merge['ready']))}",
        f"missing_inputs={','.join(merge['missing_inputs']) if merge['missing_inputs'] else '-'}",
    ])
    if merge.get('command_hint'):
        lines.append(f"command_hint={merge['command_hint']}")

    lines.extend([
        '',
        '[triage_hints]',
    ])
    for item in summary['triage_hints']:
        lines.append(item)

    lines.extend([
        '',
        '[notes]',
        '1. 先看 bundle_summary.json / bundle_summary.txt，再看 supervisor/last_fault_summary.txt。',
        '2. bundle_export_ok=1 只表示 bundle 目录与摘要已经成功写出；它不等于所有 artifacts 都齐全。',
        '3. bundle_status 只表达 artifact completeness；如果 required_ok=1 且 bundle_status=incomplete，说明缺的是 optional artifacts，而不是导出失败。',
        '4. 如果 required_ok=0，先补 supervisor run files；如果 required_ok=1 但 bundle_status=incomplete，先按 missing_optional 回到原 run_dir 补日志，再决定是否做 replay。',
        '5. 当前 Phase 1 bundle 只做稳定收集与缺失提示，不在这里重写 incident timeline 分析逻辑。',
        '',
        '[artifact_inventory]',
    ])
    for item in summary['artifacts']:
        lines.append(
            f"{item['key']} status={item['status']} required={int(bool(item['required']))} "
            f"bundle={item['bundle_path'] or '-'} source={item['source_path'] or '-'}"
        )
    return '\n'.join(lines) + '\n'


def export_run_bundle(run_dir: Path, *, bundle_dir: Optional[Path] = None) -> dict:
    run_dir = run_dir.resolve()
    manifest_path = run_dir / 'run_manifest.json'
    if not manifest_path.exists():
        raise IncidentBundleError(f'missing manifest: {manifest_path}')

    manifest = load_json(manifest_path)
    status_path = run_dir / 'process_status.json'
    status = load_json(status_path) if status_path.exists() else {}
    run_created = parse_wall_time(manifest.get('created_wall_time'))
    bundle_dir = bundle_dir.resolve() if bundle_dir is not None else default_bundle_dir(run_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[ArtifactRecord] = []

    def record_exact(
        key: str,
        group: str,
        required: bool,
        source_path: Optional[Path],
        bundle_relpath: Path,
        *,
        selection_mode: str,
        detail: str,
    ) -> None:
        artifacts.append(
            copy_artifact(
                bundle_dir,
                key=key,
                group=group,
                required=required,
                source_path=source_path,
                bundle_relpath=bundle_relpath,
                selection_mode=selection_mode,
                detail=detail,
            )
        )

    # supervisor 运行文件是 bundle 的最小真源；缺这些文件时，导出结果应直接视为 required missing。
    record_exact(
        'supervisor.run_manifest',
        'supervisor',
        True,
        run_dir / 'run_manifest.json',
        Path('supervisor') / 'run_manifest.json',
        selection_mode='run_dir',
        detail='required supervisor manifest',
    )
    record_exact(
        'supervisor.process_status',
        'supervisor',
        True,
        run_dir / 'process_status.json',
        Path('supervisor') / 'process_status.json',
        selection_mode='run_dir',
        detail='required supervisor status',
    )
    record_exact(
        'supervisor.last_fault_summary',
        'supervisor',
        True,
        run_dir / 'last_fault_summary.txt',
        Path('supervisor') / 'last_fault_summary.txt',
        selection_mode='run_dir',
        detail='required supervisor fault summary',
    )
    record_exact(
        'supervisor.supervisor_events',
        'supervisor',
        True,
        run_dir / 'supervisor_events.csv',
        Path('supervisor') / 'supervisor_events.csv',
        selection_mode='run_dir',
        detail='required supervisor event timeline',
    )

    processes = process_map(manifest)
    for name, proc in processes.items():
        log_files = proc.get('log_files') or {}
        stdout_path = log_files.get('stdout')
        stderr_path = log_files.get('stderr')
        record_exact(
            f'child_logs.{name}.stdout',
            'child_logs',
            False,
            Path(str(stdout_path)) if stdout_path else None,
            Path('child_logs') / name / 'stdout.log',
            selection_mode='manifest_log_files',
            detail=f'{name} stdout sidecar',
        )
        record_exact(
            f'child_logs.{name}.stderr',
            'child_logs',
            False,
            Path(str(stderr_path)) if stderr_path else None,
            Path('child_logs') / name / 'stderr.log',
            selection_mode='manifest_log_files',
            detail=f'{name} stderr sidecar',
        )

    nav_log_dir, nav_log_detail = resolve_nav_log_dir(manifest)
    record_exact(
        'events.uwnav_navd.nav_events',
        'events',
        False,
        None if nav_log_dir is None else nav_log_dir / 'nav_events.csv',
        Path('events') / 'uwnav_navd' / 'nav_events.csv',
        selection_mode='nav_logging_base_dir',
        detail=nav_log_detail,
    )
    record_exact(
        'nav.nav_timing',
        'nav',
        False,
        None if nav_log_dir is None else nav_log_dir / 'nav_timing.bin',
        Path('nav') / 'nav_timing.bin',
        selection_mode='nav_logging_base_dir',
        detail=nav_log_detail,
    )
    record_exact(
        'nav.nav_state',
        'nav',
        False,
        None if nav_log_dir is None else nav_log_dir / 'nav_state.bin',
        Path('nav') / 'nav_state.bin',
        selection_mode='nav_logging_base_dir',
        detail=nav_log_detail,
    )
    record_exact(
        'nav.nav_bin',
        'nav',
        False,
        None if nav_log_dir is None else nav_log_dir / 'nav.bin',
        Path('nav') / 'nav.bin',
        selection_mode='nav_logging_base_dir',
        detail=nav_log_detail,
    )

    ctrl_roots = resolve_ctrl_log_roots(manifest)
    nav_view_event, nav_view_mode = first_existing_with_mode(
        [(root / 'nav' / 'nav_events.csv', mode) for root, mode in ctrl_roots]
    )
    record_exact(
        'events.nav_viewd.nav_events',
        'events',
        False,
        nav_view_event,
        Path('events') / 'nav_viewd' / 'nav_events.csv',
        selection_mode=nav_view_mode,
        detail='nav_viewd structured event log',
    )

    control_event, control_event_mode = first_existing_with_mode(
        [(root / 'control' / 'control_events.csv', mode) for root, mode in ctrl_roots]
    )
    record_exact(
        'events.pwm_control_program.control_events',
        'events',
        False,
        control_event,
        Path('events') / 'pwm_control_program' / 'control_events.csv',
        selection_mode=control_event_mode,
        detail='ControlGuard structured event log',
    )

    comm_event, comm_event_mode = first_existing_with_mode(
        [(root / 'comm' / 'comm_events.csv', mode) for root, mode in ctrl_roots]
    )
    record_exact(
        'events.gcs_server.comm_events',
        'events',
        False,
        comm_event,
        Path('events') / 'gcs_server' / 'comm_events.csv',
        selection_mode=comm_event_mode,
        detail='gcs_server structured event log',
    )

    control_loop_path, control_loop_mode = select_latest_matching(
        ctrl_roots,
        'control/control_loop_*.csv',
        run_created=run_created,
    )
    record_exact(
        'control.control_loop',
        'control',
        False,
        control_loop_path,
        Path('control') / (control_loop_path.name if control_loop_path is not None else 'control_loop.csv'),
        selection_mode=control_loop_mode,
        detail='latest control loop log after run start',
    )

    telemetry_timeline_path, telemetry_timeline_mode = select_latest_matching(
        ctrl_roots,
        'telemetry/telemetry_timeline_*.csv',
        run_created=run_created,
    )
    record_exact(
        'telemetry.telemetry_timeline',
        'telemetry',
        False,
        telemetry_timeline_path,
        Path('telemetry') / (
            telemetry_timeline_path.name if telemetry_timeline_path is not None else 'telemetry_timeline.csv'
        ),
        selection_mode=telemetry_timeline_mode,
        detail='latest telemetry timeline log after run start',
    )

    telemetry_events_path, telemetry_events_mode = select_latest_matching(
        ctrl_roots,
        'telemetry/telemetry_events_*.csv',
        run_created=run_created,
    )
    record_exact(
        'telemetry.telemetry_events',
        'telemetry',
        False,
        telemetry_events_path,
        Path('telemetry') / (telemetry_events_path.name if telemetry_events_path is not None else 'telemetry_events.csv'),
        selection_mode=telemetry_events_mode,
        detail='latest telemetry events log after run start',
    )

    artifact_dicts = [item.to_dict() for item in artifacts]
    missing_required = [item.key for item in artifacts if item.required and item.status != 'copied']
    missing_optional = [item.key for item in artifacts if not item.required and item.status != 'copied']

    process_states = [
        str(proc.get('state') or '')
        for proc in status.get('processes', [])
        if isinstance(proc, dict)
    ]
    supervisor_state = str(status.get('supervisor_state') or '')
    all_not_started = bool(process_states) and all(state == 'not_started' for state in process_states)
    any_started = any(state not in {'', 'not_started'} for state in process_states)
    any_live = any(state in {'starting', 'running', 'stopping'} for state in process_states)
    last_fault_event = str(status.get('last_fault_event') or '')
    if last_fault_event == 'preflight_failed' and all_not_started:
        run_stage = 'preflight_failed_before_spawn'
        triage_hints = [
            '当前 run 在 preflight 阶段就失败了，先修复 supervisor/last_fault_summary.txt 里的阻塞项。',
            '因为 authority 子进程没有真正启动，零字节 child logs 和缺失的 nav/control/telemetry artifacts 在这里是预期现象。',
        ]
    elif any_live or supervisor_state in {'starting', 'running', 'stopping'}:
        run_stage = 'child_process_running'
        triage_hints = [
            '至少有一个 authority 子进程仍处于运行或停机过渡态，先结合 child logs、低频事件和高频日志排查当前 run。',
        ]
    elif any_started:
        run_stage = 'child_process_stopped_after_start'
        if supervisor_state == 'failed' or any(state == 'failed' for state in process_states):
            triage_hints = [
                '当前 run 在 authority 子进程阶段已经退出或失败；先结合 child logs、低频事件和高频日志做事后复盘。',
            ]
        else:
            triage_hints = [
                '当前 run 曾启动 authority 子进程，但导出时已经停止；先结合 child logs、低频事件和高频日志做事后复盘。',
            ]
    else:
        run_stage = 'run_created_without_child_start'
        triage_hints = [
            '当前 run 没有进入正常子进程启动阶段，先看 supervisor/last_fault_summary.txt 和 supervisor_events.csv。',
        ]

    copied_lookup = {item['key']: item['bundle_path'] for item in artifact_dicts if item['status'] == 'copied'}
    merge_inputs = {
        'nav_timing': copied_lookup.get('nav.nav_timing'),
        'nav_state': copied_lookup.get('nav.nav_state'),
        'control_log': copied_lookup.get('control.control_loop'),
        'telemetry_timeline': copied_lookup.get('telemetry.telemetry_timeline'),
        'telemetry_events': copied_lookup.get('telemetry.telemetry_events'),
    }
    merge_missing = [key for key, value in merge_inputs.items() if value is None]
    merge_ready = not merge_missing and MERGE_TOOL.exists()

    command_hint = None
    if merge_ready:
        command_hint = (
            f'cd {NAV_CORE_ROOT} && python3 tools/merge_robot_timeline.py '
            f'--nav-timing {bundle_dir / merge_inputs["nav_timing"]} '
            f'--nav-state {bundle_dir / merge_inputs["nav_state"]} '
            f'--control-log {bundle_dir / merge_inputs["control_log"]} '
            f'--telemetry-timeline {bundle_dir / merge_inputs["telemetry_timeline"]} '
            f'--telemetry-events {bundle_dir / merge_inputs["telemetry_events"]} '
            f'--bundle-dir {bundle_dir / "replay_bundle"}'
        )

    bundle_status = 'complete' if not missing_required and not missing_optional else 'incomplete'
    if missing_required:
        triage_hints.append(
            'bundle 已成功导出，但 required artifacts 缺失；当前最小 supervisor 复盘集合还不完整。'
        )
    elif missing_optional:
        triage_hints.append(
            'bundle 已成功导出；当前 incomplete 只表示 optional artifacts 缺失，不等于 bundle 导出失败。'
        )
    else:
        triage_hints.append(
            'bundle 已成功导出，当前 required/optional artifacts 都已就位。'
        )

    summary = {
        'run_id': manifest.get('run_id'),
        'profile': manifest.get('profile'),
        'run_dir': str(run_dir),
        'bundle_dir': str(bundle_dir),
        'last_fault_event': last_fault_event or None,
        'run_stage': run_stage,
        'triage_hints': triage_hints,
        'bundle_exported_wall_time': wall_time_now(),
        'bundle_export_ok': True,
        'bundle_status': bundle_status,
        'bundle_status_meaning': 'artifact_completeness',
        'bundle_incomplete': bool(missing_required or missing_optional),
        'required_ok': not missing_required,
        'missing_required_keys': missing_required,
        'missing_optional_keys': missing_optional,
        'start_here': [
            'bundle_summary.txt',
            'supervisor/last_fault_summary.txt',
            'supervisor/process_status.json',
            'supervisor/supervisor_events.csv',
        ],
        'bundle_rules': {
            'required_keys': [item.key for item in artifacts if item.required],
            'optional_keys': [item.key for item in artifacts if not item.required],
            'missing_marks_incomplete': True,
            'notes': [
                'required 只包含 supervisor run files；这些文件缺失时无法做最小问题复盘。',
                'optional 包含 child logs、事件日志和高频日志；缺失时 bundle 仍导出，但会明确标成 incomplete。',
                '高频日志只做复制，不改原始 bin/csv 格式，也不在这里做二次分析。',
            ],
        },
        'merge_robot_timeline': {
            'ready': merge_ready,
            'tool_path': str(MERGE_TOOL),
            'inputs': merge_inputs,
            'missing_inputs': merge_missing,
            'command_hint': command_hint,
        },
        'artifacts': artifact_dicts,
    }

    safe_write_json(bundle_dir / 'bundle_summary.json', summary)
    safe_write_text(bundle_dir / 'bundle_summary.txt', build_text_summary(summary))
    return summary
