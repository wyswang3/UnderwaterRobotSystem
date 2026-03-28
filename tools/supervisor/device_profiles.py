#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

DEVICE_TYPES = ('imu', 'volt32', 'dvl', 'usbl', 'unknown')
AUTO_PROFILE = 'auto'


@dataclass(frozen=True)
class StartupProfileSpec:
    name: str
    description: str
    launch_mode: str
    implemented: bool
    required_devices: tuple[str, ...]
    optional_devices: tuple[str, ...]
    start_modules: tuple[str, ...]
    skip_modules: tuple[str, ...]
    allowed_capabilities: tuple[str, ...]
    allowed_logs: tuple[str, ...]
    disabled_capabilities: tuple[str, ...]


# 启动 profile 先作为外围策略和记录面落地，这一轮不直接重写 authority 进程图。
PROFILE_SPECS: dict[str, StartupProfileSpec] = {
    'no_sensor': StartupProfileSpec(
        name='no_sensor',
        description='No trusted sensor detected; stay in inspection-only mode.',
        launch_mode='preflight_only',
        implemented=True,
        required_devices=(),
        optional_devices=(),
        start_modules=(
            'device_identification',
            'usb_serial_snapshot',
            'phase0_supervisor preflight',
        ),
        skip_modules=(
            'uwnav_navd',
            'nav_viewd',
            'pwm_control_program',
            'gcs_server',
        ),
        allowed_capabilities=(
            'serial inventory snapshot',
            'binding ambiguity review',
            'incident bundle export from failure-path run',
        ),
        allowed_logs=(
            'device_identification summary',
            'usb_serial_snapshot output',
            'supervisor preflight events',
        ),
        disabled_capabilities=(
            'nav state publication',
            'control loop bring-up',
            'field authority startup',
        ),
    ),
    'volt_only': StartupProfileSpec(
        name='volt_only',
        description='Voltage board only; allow power diagnostics without nav/control bring-up.',
        launch_mode='preflight_only',
        implemented=True,
        required_devices=('volt32',),
        optional_devices=(),
        start_modules=(
            'device_identification',
            'usb_serial_snapshot',
            'volt32_data_verifier',
        ),
        skip_modules=(
            'uwnav_navd',
            'nav_viewd',
            'pwm_control_program',
            'gcs_server',
        ),
        allowed_capabilities=(
            'power rail capture',
            'serial wiring validation',
            'voltage channel logging',
        ),
        allowed_logs=(
            'device_identification summary',
            'volt32 csv logs',
            'usb serial snapshot',
        ),
        disabled_capabilities=(
            'nav state publication',
            'control intent bridge',
            'auto / closed-loop control',
        ),
    ),
    'imu_only': StartupProfileSpec(
        name='imu_only',
        description='IMU present and DVL absent; allow bench-safe degraded nav bring-up.',
        launch_mode='bench_safe_smoke',
        implemented=True,
        required_devices=('imu',),
        optional_devices=('volt32',),
        start_modules=(
            'phase0_supervisor bench',
            'uwnav_navd',
            'nav_viewd',
            'pwm_control_program --pwm-dummy',
            'gcs_server',
        ),
        skip_modules=('external_dvl_capture', 'usbl_ingest'),
        allowed_capabilities=(
            'imu bind validation',
            'degraded nav publication',
            'nav/control/gcs bring-up under --pwm-dummy',
            'incident bundle capture',
        ),
        allowed_logs=(
            'supervisor run files',
            'child logs',
            'nav_events.csv',
            'control_events.csv',
            'nav_timing.bin',
            'nav_state.bin',
        ),
        disabled_capabilities=(
            'dvl-assisted velocity / position confidence',
            'field release',
            'real PWM authority',
        ),
    ),
    'imu_dvl': StartupProfileSpec(
        name='imu_dvl',
        description='IMU + DVL available; this is the preferred bench-safe smoke profile.',
        launch_mode='bench_safe_smoke',
        implemented=True,
        required_devices=('imu', 'dvl'),
        optional_devices=('volt32',),
        start_modules=(
            'phase0_supervisor bench',
            'uwnav_navd',
            'nav_viewd',
            'pwm_control_program --pwm-dummy',
            'gcs_server',
        ),
        skip_modules=('usbl_ingest',),
        allowed_capabilities=(
            'imu + dvl binding validation',
            'bench-safe nav publication',
            'bridge/control dummy path smoke',
            'incident bundle / replay preparation',
        ),
        allowed_logs=(
            'supervisor run files',
            'child logs',
            'nav_events.csv',
            'control_events.csv',
            'nav_timing.bin',
            'nav_state.bin',
            'telemetry logs when present',
        ),
        disabled_capabilities=(
            'usbl-aided localization',
            'real PWM authority',
            'field autonomy release',
        ),
    ),
    'imu_dvl_usbl': StartupProfileSpec(
        name='imu_dvl_usbl',
        description='Reserved for IMU + DVL + USBL integrated bring-up once USBL path is stable.',
        launch_mode='reserved',
        implemented=False,
        required_devices=('imu', 'dvl', 'usbl'),
        optional_devices=('volt32',),
        start_modules=(
            'phase0_supervisor bench',
            'uwnav_navd',
            'nav_viewd',
            'pwm_control_program --pwm-dummy',
            'gcs_server',
            'future usbl ingest',
        ),
        skip_modules=(),
        allowed_capabilities=(
            'future multi-sensor bring-up planning',
            'binding review for usb re-enumeration',
        ),
        allowed_logs=(
            'all imu_dvl logs',
            'future usbl diagnostics',
        ),
        disabled_capabilities=(
            'production release before USBL interface is validated',
            'real PWM authority',
        ),
    ),
    'full_stack': StartupProfileSpec(
        name='full_stack',
        description='Reserved for the eventual IMU + DVL + USBL + Volt32 field stack.',
        launch_mode='reserved',
        implemented=False,
        required_devices=('imu', 'dvl', 'usbl', 'volt32'),
        optional_devices=(),
        start_modules=(
            'phase0_supervisor bench',
            'uwnav_navd',
            'nav_viewd',
            'pwm_control_program',
            'gcs_server',
            'future usbl / telemetry extensions',
        ),
        skip_modules=(),
        allowed_capabilities=(
            'future integrated field startup planning',
            'full diagnostics / logging checklist',
        ),
        allowed_logs=(
            'all current logs',
            'future USBL logs',
            'future field checklists',
        ),
        disabled_capabilities=(
            'automatic enablement in this round',
            'authority rewiring in phase0 supervisor',
        ),
    ),
}

PROFILE_NAVIGATION_REQUIREMENTS: dict[str, str] = {
    'no_sensor': 'disabled',
    'volt_only': 'disabled',
    'imu_only': 'required',
    'imu_dvl': 'required',
    'imu_dvl_usbl': 'required',
    'full_stack': 'required',
}

PROFILE_RUNTIME_LEVEL_HINTS: dict[str, str] = {
    'no_sensor': 'control_only',
    'volt_only': 'control_only',
    'imu_only': 'control_nav_optional',
    'imu_dvl': 'control_nav_optional',
    'imu_dvl_usbl': 'full_stack_preview',
    'full_stack': 'full_stack_preview',
}

# 启动 profile 负责表达“当前设备 readiness”，而操作员真正看到的能力等级要更保守：
# - IMU-only 只应解释成 attitude_feedback，不能写成完整导航；
# - IMU + DVL 只应解释成 relative_nav，不能写成绝对定位；
# - DVL 是外接可拆模块，因此不是默认 control_only 的硬依赖。
PROFILE_CAPABILITY_LEVELS: dict[str, str] = {
    'no_sensor': 'control_only',
    'volt_only': 'control_only',
    'imu_only': 'attitude_feedback',
    'imu_dvl': 'relative_nav',
    'imu_dvl_usbl': 'full_stack_preview',
    'full_stack': 'full_stack_preview',
}

PROFILE_CAPABILITY_SUMMARIES: dict[str, str] = {
    'control_only': '不宣称导航；当前只保证遥控、状态观察、日志记录和 bundle 导出。',
    'attitude_feedback': 'IMU-only 只提供姿态反馈与运动分析，不宣称完整导航。',
    'relative_nav': 'IMU + DVL 只提供速度与短时相对运动信息，不宣称绝对定位。',
    'full_stack_preview': '仅保留预留预览口径，当前不进入默认 operator lane。',
}

PROFILE_EXPECTED_MOTION_FIELDS: dict[str, tuple[str, ...]] = {
    'control_only': (),
    'attitude_feedback': ('roll', 'pitch', 'yaw', 'gyro', 'accel'),
    'relative_nav': ('roll', 'pitch', 'yaw', 'gyro', 'accel', 'velocity', 'relative_position'),
    'full_stack_preview': ('roll', 'pitch', 'yaw', 'gyro', 'accel', 'velocity', 'relative_position'),
}


def startup_profile_navigation_requirement(name: str) -> str:
    key = (name or '').strip().lower()
    return PROFILE_NAVIGATION_REQUIREMENTS.get(key, 'required')


def startup_profile_runtime_level_hint(name: str) -> str:
    key = (name or '').strip().lower()
    return PROFILE_RUNTIME_LEVEL_HINTS.get(key, 'control_nav_optional')


def startup_profile_capability_level(name: str) -> str:
    key = (name or '').strip().lower()
    return PROFILE_CAPABILITY_LEVELS.get(key, 'control_only')


def capability_level_summary(level: str) -> str:
    key = (level or 'control_only').strip().lower()
    return PROFILE_CAPABILITY_SUMMARIES.get(key, PROFILE_CAPABILITY_SUMMARIES['control_only'])


def startup_profile_capability_summary(name: str) -> str:
    return capability_level_summary(startup_profile_capability_level(name))


def capability_level_motion_fields(level: str) -> tuple[str, ...]:
    key = (level or 'control_only').strip().lower()
    return PROFILE_EXPECTED_MOTION_FIELDS.get(key, ())


def startup_profile_motion_fields(name: str) -> tuple[str, ...]:
    return capability_level_motion_fields(startup_profile_capability_level(name))


def normalize_device_type(value: str) -> str:
    device_type = (value or 'unknown').strip().lower()
    return device_type if device_type in DEVICE_TYPES else 'unknown'


def empty_device_counts() -> dict[str, int]:
    return {device_type: 0 for device_type in DEVICE_TYPES}


def count_device_types(devices: Iterable[Mapping[str, object] | str]) -> dict[str, int]:
    counts = empty_device_counts()
    for item in devices:
        if isinstance(item, str):
            device_type = normalize_device_type(item)
        else:
            raw_type = str(item.get('device_type') or 'unknown')
            if item.get('ambiguous'):
                raw_type = 'unknown'
            device_type = normalize_device_type(raw_type)
        counts[device_type] += 1
    return counts


def summarize_device_counts(device_counts: Mapping[str, int]) -> str:
    parts = []
    for device_type in ('imu', 'dvl', 'usbl', 'volt32', 'unknown'):
        count = int(device_counts.get(device_type, 0) or 0)
        parts.append(f'{device_type}={count}')
    return ', '.join(parts)


def get_profile_spec(name: str) -> StartupProfileSpec:
    key = (name or '').strip().lower()
    if key not in PROFILE_SPECS:
        raise ValueError(f'unsupported startup profile: {name}')
    return PROFILE_SPECS[key]


def recommend_startup_profile(device_counts: Mapping[str, int]) -> dict:
    imu_count = int(device_counts.get('imu', 0) or 0)
    dvl_count = int(device_counts.get('dvl', 0) or 0)
    usbl_count = int(device_counts.get('usbl', 0) or 0)
    volt_count = int(device_counts.get('volt32', 0) or 0)

    if imu_count and dvl_count and usbl_count and volt_count:
        profile_name = 'full_stack'
        reason = 'IMU、DVL、USBL 和 Volt32 都已识别，满足 full_stack 预留设计的最小设备集合。'
    elif imu_count and dvl_count and usbl_count:
        profile_name = 'imu_dvl_usbl'
        reason = 'IMU、DVL 和 USBL 均已识别，但 Volt32 还不是 full_stack 的必需前提。'
    elif imu_count and dvl_count:
        profile_name = 'imu_dvl'
        reason = 'IMU 与 DVL 均在线，适合当前 bench safe smoke 的优先组合。'
    elif imu_count:
        profile_name = 'imu_only'
        reason = 'IMU 已在线，但 DVL 未识别；应按退化导航 bring-up 处理。'
    elif volt_count:
        profile_name = 'volt_only'
        reason = '只识别到 Volt32，适合先做供电和串口链路诊断。'
    else:
        profile_name = 'no_sensor'
        reason = '没有识别到可信绑定的 IMU/DVL/USBL/Volt32 设备，应停在 preflight。'

    spec = get_profile_spec(profile_name)
    capability_level = startup_profile_capability_level(spec.name)
    return {
        'profile': spec.name,
        'description': spec.description,
        'launch_mode': spec.launch_mode,
        'implemented': spec.implemented,
        'navigation_requirement': startup_profile_navigation_requirement(spec.name),
        'runtime_level_hint': startup_profile_runtime_level_hint(spec.name),
        'capability_level': capability_level,
        'capability_summary': startup_profile_capability_summary(spec.name),
        'motion_fields_expected': list(capability_level_motion_fields(capability_level)),
        'reason': reason,
        'device_summary': summarize_device_counts(device_counts),
    }


def resolve_startup_profile(requested: str, device_counts: Mapping[str, int]) -> dict:
    recommended = recommend_startup_profile(device_counts)
    requested_name = (requested or AUTO_PROFILE).strip().lower()
    if requested_name in ('', AUTO_PROFILE):
        selected_name = recommended['profile']
        source = 'auto'
    else:
        selected_name = requested_name
        source = 'requested'

    spec = get_profile_spec(selected_name)
    missing_required = [
        device_type
        for device_type in spec.required_devices
        if int(device_counts.get(device_type, 0) or 0) <= 0
    ]

    warnings: list[str] = []
    if spec.launch_mode == 'preflight_only':
        warnings.append('当前 startup profile 只建议 preflight / 独立采样，不直接放行 bench authority 链。')
    if spec.launch_mode == 'reserved':
        warnings.append('当前 startup profile 仍是预留设计，尚未接入 phase0 supervisor 的进程选择。')

    errors: list[str] = []
    if missing_required:
        errors.append('missing required devices: ' + ', '.join(missing_required))

    capability_level = startup_profile_capability_level(spec.name)
    return {
        'requested': requested_name or AUTO_PROFILE,
        'selected': spec.name,
        'source': source,
        'description': spec.description,
        'launch_mode': spec.launch_mode,
        'implemented': spec.implemented,
        'navigation_requirement': startup_profile_navigation_requirement(spec.name),
        'runtime_level_hint': startup_profile_runtime_level_hint(spec.name),
        'capability_level': capability_level,
        'capability_summary': startup_profile_capability_summary(spec.name),
        'motion_fields_expected': list(capability_level_motion_fields(capability_level)),
        'recommended': recommended,
        'missing_required_devices': missing_required,
        'warnings': warnings,
        'errors': errors,
        'device_summary': summarize_device_counts(device_counts),
    }


def serialize_profile_catalog() -> list[dict]:
    catalog: list[dict] = []
    for name in ('no_sensor', 'volt_only', 'imu_only', 'imu_dvl', 'imu_dvl_usbl', 'full_stack'):
        spec = PROFILE_SPECS[name]
        catalog.append(
            {
                'name': spec.name,
                'description': spec.description,
                'launch_mode': spec.launch_mode,
                'implemented': spec.implemented,
                'required_devices': list(spec.required_devices),
                'optional_devices': list(spec.optional_devices),
                'navigation_requirement': startup_profile_navigation_requirement(spec.name),
                'runtime_level_hint': startup_profile_runtime_level_hint(spec.name),
                'capability_level': startup_profile_capability_level(spec.name),
                'capability_summary': startup_profile_capability_summary(spec.name),
                'motion_fields_expected': list(startup_profile_motion_fields(spec.name)),
                'start_modules': list(spec.start_modules),
                'skip_modules': list(spec.skip_modules),
                'allowed_capabilities': list(spec.allowed_capabilities),
                'allowed_logs': list(spec.allowed_logs),
                'disabled_capabilities': list(spec.disabled_capabilities),
            }
        )
    return catalog
