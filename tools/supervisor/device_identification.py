#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import pathlib
import re
import time
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from tools.supervisor import device_profiles

DEFAULT_RULES_PATH = pathlib.Path(__file__).with_name('device_identification_rules.json')
DEFAULT_SAMPLE_POLICY = 'auto'
DEFAULT_SAMPLE_WINDOW_S = 0.35
DEFAULT_MAX_SAMPLE_BYTES = 2048
DEFAULT_DYNAMIC_BAUDS = (230400, 115200)
MIN_RESOLVE_SCORE = 0.60
AMBIGUOUS_SCORE_DELTA = 0.12
STATIC_IDENTITY_FIELD_KEYS = (
    'by_id',
    'vendor_id',
    'product_id',
    'serial',
    'manufacturer',
    'product',
)
KNOWN_IMU_FRAME_TYPES = {0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x5B, 0x5C}
SUPPORT_RANK = {
    'candidate_only': 0,
    'partial': 1,
    'sample_backed': 2,
}
CHANNEL_LINE_RE = re.compile(
    r'(?:^|[\r\n])\s*CH(?P<index>\d{1,2})\s*:\s*'
    r'(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+))(?:\s*(?P<unit>[A-Za-z%]+))?',
    re.IGNORECASE,
)
DVL_REPLY_TOKEN_RE = re.compile(r'(?:^|[\r\n"\x00:])(?P<token>SA|TS|BI|BS|BE|BD)\s*,', re.IGNORECASE)
DVL_COMMAND_TOKEN_RE = re.compile(r'(?:^|[\r\n"\x00:])(?P<token>CS|CZ)\b', re.IGNORECASE)
DVL_SENSOR_ID_RE = re.compile(r'\bDVL_H\d+\b', re.IGNORECASE)
CSV_UNIT_VALUE_RE = re.compile(r'^\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s*(?P<unit>[A-Za-z%]+)\s*$')
USBL_TOKEN_RE = re.compile(r'\bUSBL\b', re.IGNORECASE)
IMU_EXPORT_CORE_COLUMNS = (
    'AccX',
    'AccY',
    'AccZ',
    'AsX',
    'AsY',
    'AsZ',
    'HX',
    'HY',
    'HZ',
    'AngX',
    'AngY',
    'AngZ',
)
IMU_EXPORT_TIME_COLUMNS = ('MonoNS', 'EstNS')
IMU_ARCHIVE_HEADER_MARKERS = (
    'ax(g)',
    'ay(g)',
    'az(g)',
    'wx(deg/s)',
    'wy(deg/s)',
    'wz(deg/s)',
    'anglex(deg)',
    'angley(deg)',
    'anglez(deg)',
    'magx',
    'magy',
    'magz',
)


@dataclass(frozen=True)
class DeviceRule:
    device_type: str
    display_name: str
    by_id_contains: tuple[str, ...] = ()
    vendor_ids: tuple[str, ...] = ()
    product_ids: tuple[str, ...] = ()
    serial_contains: tuple[str, ...] = ()
    manufacturer_contains: tuple[str, ...] = ()
    product_contains: tuple[str, ...] = ()
    baud_candidates: tuple[int, ...] = ()
    static_support: str = 'candidate_only'
    dynamic_support: str = 'candidate_only'
    by_id_support: str = 'candidate_only'
    vendor_id_support: str = 'candidate_only'
    product_id_support: str = 'candidate_only'
    serial_support: str = 'candidate_only'
    manufacturer_support: str = 'candidate_only'
    product_support: str = 'candidate_only'
    static_sample_gaps: tuple[str, ...] = ()
    dynamic_sample_gaps: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatchScore:
    device_type: str
    score: float
    evidence: tuple[str, ...]
    source: str
    support_level: str = 'candidate_only'
    detector: str = ''


def wall_time_now() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime())


def trim_text(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding='utf-8').strip()
    except OSError:
        return ''


def lowercase(value: str) -> str:
    return value.lower()


def normalize_tuple(values: Iterable[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    items = []
    for value in values:
        text = str(value or '').strip().lower()
        if text:
            items.append(text)
    return tuple(items)


def normalize_notes(values: Iterable[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    notes = []
    for value in values:
        text = str(value or '').strip()
        if text:
            notes.append(text)
    return tuple(notes)


def resolve_tty_name(path: pathlib.Path) -> str:
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path
    return resolved.name or path.name


def load_rules(path: pathlib.Path | None = None) -> list[DeviceRule]:
    rules_path = path or DEFAULT_RULES_PATH
    raw = json.loads(rules_path.read_text(encoding='utf-8'))
    devices = raw.get('devices', [])
    rules: list[DeviceRule] = []
    for item in devices:
        sample_support = item.get('sample_support') or {}
        static_field_support = item.get('static_field_support') or {}
        sample_gaps = item.get('sample_gaps') or {}
        rules.append(
            DeviceRule(
                device_type=str(item.get('device_type') or 'unknown').strip().lower(),
                display_name=str(item.get('display_name') or item.get('device_type') or 'unknown').strip(),
                by_id_contains=normalize_tuple(item.get('by_id_contains')),
                vendor_ids=normalize_tuple(item.get('vendor_ids')),
                product_ids=normalize_tuple(item.get('product_ids')),
                serial_contains=normalize_tuple(item.get('serial_contains')),
                manufacturer_contains=normalize_tuple(item.get('manufacturer_contains')),
                product_contains=normalize_tuple(item.get('product_contains')),
                baud_candidates=tuple(int(value) for value in item.get('baud_candidates', []) if int(value) > 0),
                static_support=_normalize_support_level(str(sample_support.get('static_identity') or 'candidate_only')),
                dynamic_support=_normalize_support_level(str(sample_support.get('dynamic_probe') or 'candidate_only')),
                by_id_support=_normalize_support_level(static_field_support.get('by_id') or sample_support.get('static_identity') or 'candidate_only'),
                vendor_id_support=_normalize_support_level(static_field_support.get('vendor_id') or sample_support.get('static_identity') or 'candidate_only'),
                product_id_support=_normalize_support_level(static_field_support.get('product_id') or sample_support.get('static_identity') or 'candidate_only'),
                serial_support=_normalize_support_level(static_field_support.get('serial') or sample_support.get('static_identity') or 'candidate_only'),
                manufacturer_support=_normalize_support_level(static_field_support.get('manufacturer') or sample_support.get('static_identity') or 'candidate_only'),
                product_support=_normalize_support_level(static_field_support.get('product') or sample_support.get('static_identity') or 'candidate_only'),
                static_sample_gaps=normalize_notes(sample_gaps.get('static_identity')),
                dynamic_sample_gaps=normalize_notes(sample_gaps.get('dynamic_probe')),
                notes=normalize_notes(item.get('notes')),
            )
        )
    return rules


def _read_sysfs_identity(current: pathlib.Path) -> dict[str, str]:
    return {
        'vendor_id': lowercase(trim_text(current / 'idVendor')),
        'product_id': lowercase(trim_text(current / 'idProduct')),
        'serial': trim_text(current / 'serial'),
        'manufacturer': trim_text(current / 'manufacturer'),
        'product': trim_text(current / 'product'),
    }


def load_identity(path: pathlib.Path, sys_root: pathlib.Path) -> dict:
    tty_name = resolve_tty_name(path)
    identity = {
        'path': str(path),
        'canonical_path': str(path.resolve(strict=False)),
        'tty_name': tty_name,
        'by_id_name': path.name if 'by-id' in str(path.parent) else '',
        'vendor_id': '',
        'product_id': '',
        'serial': '',
        'manufacturer': '',
        'product': '',
    }
    if not tty_name:
        return identity

    current = (sys_root / tty_name / 'device').resolve(strict=False)
    visited: set[pathlib.Path] = set()
    while current not in visited and current != current.parent:
        visited.add(current)
        snapshot = _read_sysfs_identity(current)
        for key, value in snapshot.items():
            if value and not identity[key]:
                identity[key] = value
        if all(identity[key] for key in ('vendor_id', 'product_id', 'serial', 'manufacturer', 'product')):
            break
        current = current.parent
    return identity


def discover_paths(dev_root: pathlib.Path) -> Iterable[pathlib.Path]:
    by_id = dev_root / 'serial' / 'by-id'
    if by_id.exists() and by_id.is_dir():
        for entry in sorted(by_id.iterdir()):
            if entry.is_symlink() or entry.is_char_device():
                yield entry

    for entry in sorted(dev_root.iterdir()):
        name = entry.name
        if name.startswith('ttyUSB') or name.startswith('ttyACM'):
            yield entry


def scan_serial_snapshot(dev_root: pathlib.Path, sys_root: pathlib.Path) -> list[dict]:
    devices: list[dict] = []
    seen: set[str] = set()
    for path in discover_paths(dev_root):
        identity = load_identity(path, sys_root)
        key = identity['canonical_path'] or identity['path']
        if key in seen:
            continue
        seen.add(key)
        devices.append(identity)
    return devices


def _contains_any(text: str, markers: Sequence[str]) -> tuple[bool, list[str]]:
    haystack = (text or '').strip().lower()
    hits = [marker for marker in markers if marker and marker in haystack]
    return bool(hits), hits


def _normalize_support_level(value: str) -> str:
    support = (value or 'candidate_only').strip().lower()
    return support if support in SUPPORT_RANK else 'candidate_only'


def _best_support_level(left: str, right: str) -> str:
    left_norm = _normalize_support_level(left)
    right_norm = _normalize_support_level(right)
    return left_norm if SUPPORT_RANK[left_norm] >= SUPPORT_RANK[right_norm] else right_norm


def serialize_match(match: MatchScore | None) -> Optional[dict]:
    if match is None:
        return None
    return {
        'device_type': match.device_type,
        'score': round(match.score, 3),
        'evidence': list(match.evidence),
        'source': match.source,
        'support_level': match.support_level,
        'detector': match.detector,
    }


def serialize_static_field_support(rule: DeviceRule) -> dict[str, str]:
    return {
        'by_id': rule.by_id_support,
        'vendor_id': rule.vendor_id_support,
        'product_id': rule.product_id_support,
        'serial': rule.serial_support,
        'manufacturer': rule.manufacturer_support,
        'product': rule.product_support,
    }


# 规则成熟度需要和实时扫描一起暴露，方便在 bench 前明确区分“可直接依赖”和“仍需补样本”的静态身份条件。
def serialize_rule_catalog(rules: Sequence[DeviceRule]) -> list[dict]:
    catalog = []
    for rule in rules:
        catalog.append(
            {
                'device_type': rule.device_type,
                'display_name': rule.display_name,
                'static_identity': {
                    'overall_support': rule.static_support,
                    'field_support': serialize_static_field_support(rule),
                    'sample_gaps': list(rule.static_sample_gaps),
                },
                'dynamic_probe': {
                    'overall_support': rule.dynamic_support,
                    'sample_gaps': list(rule.dynamic_sample_gaps),
                },
                'notes': list(rule.notes),
            }
        )
    return catalog


def summarize_rule_catalog(catalog: Sequence[dict], *, device_types: Sequence[str] = ('imu', 'dvl', 'volt32')) -> str:
    parts = []
    wanted = set(device_types)
    for item in catalog:
        if item.get('device_type') not in wanted:
            continue
        static = item.get('static_identity', {}).get('overall_support', 'unknown')
        dynamic = item.get('dynamic_probe', {}).get('overall_support', 'unknown')
        parts.append(f"{item['device_type']} static={static} dynamic={dynamic}")
    return '; '.join(parts)


def summarize_static_sample_gaps(catalog: Sequence[dict], *, device_types: Sequence[str] = ('imu', 'dvl', 'volt32')) -> str:
    parts = []
    wanted = set(device_types)
    for item in catalog:
        if item.get('device_type') not in wanted:
            continue
        gaps = list(item.get('static_identity', {}).get('sample_gaps') or [])
        if gaps:
            parts.append(f"{item['device_type']}: {gaps[0]}")
    return '; '.join(parts)


def _extract_header_fields(text: str) -> list[str]:
    for raw_line in text.splitlines():
        line = raw_line.strip().strip('\ufeff')
        if not line:
            continue
        if ',' in line:
            return [part.strip().strip('"') for part in line.split(',')]
        if '\t' in line:
            return [part.strip().strip('"') for part in line.split('\t')]
        return [line]
    return []


def _header_field_set(header: Sequence[str]) -> set[str]:
    return {item.strip().lower() for item in header if item and item.strip()}


def _header_contains_all(header: Sequence[str], expected: Sequence[str]) -> bool:
    fields = _header_field_set(header)
    return all(item.strip().lower() in fields for item in expected)


def _extract_channel_header_indices(header: Sequence[str]) -> list[int]:
    indices = []
    for item in header:
        match = re.fullmatch(r'CH(?P<index>\d{1,2})', item.strip(), re.IGNORECASE)
        if match is None:
            continue
        indices.append(int(match.group('index')))
    return sorted(set(indices))


def _has_contiguous_channels(header: Sequence[str], count: int) -> bool:
    indices = _extract_channel_header_indices(header)
    return indices[:count] == list(range(count))


def _extract_csv_value_units(text: str, max_rows: int = 4) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= 1:
        return []
    units: set[str] = set()
    for row in lines[1 : 1 + max_rows]:
        for cell in row.split(','):
            match = CSV_UNIT_VALUE_RE.match(cell.strip().strip('"'))
            if match is None:
                continue
            unit = match.group('unit').upper()
            if unit:
                units.add(unit)
    return sorted(units)


def _merge_candidate(match_map: dict[str, MatchScore], match: MatchScore) -> None:
    existing = match_map.get(match.device_type)
    if existing is None:
        match_map[match.device_type] = match
        return

    evidence = list(existing.evidence)
    for item in match.evidence:
        if item not in evidence:
            evidence.append(item)

    score = max(existing.score, match.score)
    detector = existing.detector if existing.score >= match.score else match.detector
    support_level = _best_support_level(existing.support_level, match.support_level)
    match_map[match.device_type] = MatchScore(
        device_type=match.device_type,
        score=score,
        evidence=tuple(evidence),
        source=existing.source,
        support_level=support_level,
        detector=detector,
    )


def _count_legacy_wit_sync_frames(sample: bytes) -> tuple[int, int]:
    valid = 0
    loose = 0
    for index in range(len(sample) - 10):
        if sample[index] != 0x55 or sample[index + 1] not in KNOWN_IMU_FRAME_TYPES:
            continue
        loose += 1
        frame = sample[index : index + 11]
        if len(frame) == 11 and (sum(frame[:10]) & 0xFF) == frame[10]:
            valid += 1
    return valid, loose


def score_static_identity(identity: dict, rule: DeviceRule) -> Optional[MatchScore]:
    score = 0.0
    evidence: list[str] = []

    matched, hits = _contains_any(identity.get('by_id_name', ''), rule.by_id_contains)
    if matched:
        score += 0.55
        evidence.append(f'by-id contains {hits[0]}')

    vendor_id = str(identity.get('vendor_id') or '').lower()
    product_id = str(identity.get('product_id') or '').lower()
    if vendor_id and vendor_id in rule.vendor_ids:
        score += 0.15
        evidence.append(f'vid={vendor_id}')
    if product_id and product_id in rule.product_ids:
        score += 0.20
        evidence.append(f'pid={product_id}')

    matched, hits = _contains_any(identity.get('serial', ''), rule.serial_contains)
    if matched:
        score += 0.10
        evidence.append(f'serial contains {hits[0]}')

    matched, hits = _contains_any(identity.get('manufacturer', ''), rule.manufacturer_contains)
    if matched:
        score += 0.10
        evidence.append(f'manufacturer contains {hits[0]}')

    matched, hits = _contains_any(identity.get('product', ''), rule.product_contains)
    if matched:
        score += 0.10
        evidence.append(f'product contains {hits[0]}')

    if score <= 0.0:
        return None
    return MatchScore(
        device_type=rule.device_type,
        score=min(score, 0.95),
        evidence=tuple(evidence),
        source='static',
        support_level=_normalize_support_level(rule.static_support),
        detector='static_identity',
    )


def _classify_dvl_sample(text: str) -> Optional[MatchScore]:
    header = _extract_header_fields(text)
    token_hits = sorted(set(token.upper() for token in DVL_REPLY_TOKEN_RE.findall(text)))
    evidence: list[str] = []
    score = 0.0
    detector = ''

    if _header_contains_all(header, ('Timestamp(s)', 'SensorID', 'RawLine')):
        score = 0.74
        detector = 'dvl_export_rawline_csv'
        evidence.append('sample-backed DVL raw-line CSV header present')
        if DVL_SENSOR_ID_RE.search(text):
            score = 0.78
            evidence.append('sample-backed SensorID matches DVL_H*')

    if token_hits:
        distinct_count = len(token_hits)
        if distinct_count >= 3:
            token_score = min(0.94, 0.78 + 0.03 * distinct_count)
        elif distinct_count == 2:
            token_score = 0.82
        else:
            token_score = 0.68
        if token_score >= score:
            detector = 'dvl_reply_tokens'
        score = max(score, token_score)
        evidence.append('sample-backed DVL reply tokens: ' + ', '.join(token_hits))

    if score <= 0.0:
        command_hits = sorted(set(token.upper() for token in DVL_COMMAND_TOKEN_RE.findall(text)))
        if command_hits:
            return MatchScore(
                device_type='dvl',
                score=0.40,
                evidence=(f'only command echoes detected: {", ".join(command_hits)}',),
                source='dynamic',
                support_level='candidate_only',
                detector='dvl_command_echo_only',
            )
        return None

    return MatchScore(
        device_type='dvl',
        score=score,
        evidence=tuple(evidence),
        source='dynamic',
        support_level='sample_backed',
        detector=detector or 'dvl_reply_tokens',
    )


def _classify_volt32_sample(text: str) -> Optional[MatchScore]:
    header = _extract_header_fields(text)
    evidence: list[str] = []
    score = 0.0
    support_level = 'candidate_only'
    detector = ''

    if _has_contiguous_channels(header, 16):
        score = 0.78
        support_level = 'sample_backed'
        detector = 'volt32_export_csv'
        evidence.append('sample-backed Volt32 CSV header contains CH0..CH15')
        if header and header[0] in ('Timestamp', 'MonoNS'):
            score += 0.04
            evidence.append(f'timebase column={header[0]}')
        units = _extract_csv_value_units(text)
        if units:
            evidence.append('sample-backed exported value suffixes: ' + ', '.join(units))
            score += 0.05 if {'A', 'V'}.issubset(set(units)) else 0.02

    channel_hits = sorted(set(match.group('index') for match in CHANNEL_LINE_RE.finditer(text)))
    line_units = sorted(
        {
            (match.group('unit') or '').upper()
            for match in CHANNEL_LINE_RE.finditer(text)
            if (match.group('unit') or '').strip()
        }
    )
    if len(channel_hits) >= 4:
        line_score = min(0.82, 0.66 + 0.02 * min(len(channel_hits), 8))
        if line_units:
            line_score += 0.04
        if line_score >= score:
            detector = 'volt32_channel_lines'
            support_level = 'partial'
        score = max(score, line_score)
        evidence.append('CHn line grammar matches existing Volt32 parser: ' + ', '.join(f'CH{item}' for item in channel_hits[:6]))
        if line_units:
            evidence.append('line units=' + ', '.join(line_units))

    if score <= 0.0:
        return None
    return MatchScore(
        device_type='volt32',
        score=min(score, 0.89),
        evidence=tuple(evidence),
        source='dynamic',
        support_level=support_level,
        detector=detector or 'volt32_channel_lines',
    )


def _classify_imu_sample(sample: bytes, text: str) -> Optional[MatchScore]:
    header = _extract_header_fields(text)
    evidence: list[str] = []
    score = 0.0
    support_level = 'candidate_only'
    detector = ''

    # 真实样本证明导出 IMU CSV 的列集合很稳定，但这类证据主要用于离线样本校准。
    if _header_contains_all(header, IMU_EXPORT_CORE_COLUMNS):
        score = 0.84
        support_level = 'sample_backed'
        detector = 'imu_export_csv'
        evidence.append('sample-backed IMU export columns: Acc/As/H/Ang axes all present')
        if _header_contains_all(header, IMU_EXPORT_TIME_COLUMNS):
            score += 0.03
            evidence.append('MonoNS/EstNS timebase columns present')
        if 'TemperatureC'.lower() in _header_field_set(header):
            evidence.append('TemperatureC column present (current samples may be blank)')

    header_lower = _header_field_set(header)
    if not score and all(marker in header_lower for marker in IMU_ARCHIVE_HEADER_MARKERS):
        score = 0.78
        support_level = 'sample_backed'
        detector = 'imu_archive_text'
        evidence.append('sample-backed archived WIT text header contains accel/gyro/angle/mag groups')

    # 兼容保留旧 WIT UART 同步帧识别，但当前 runtime 主链是 Modbus 轮询，不能把它当主证据。
    valid_frames, loose_frames = _count_legacy_wit_sync_frames(sample)
    if valid_frames >= 2 or loose_frames >= 4:
        legacy_score = min(0.62, 0.50 + 0.03 * max(valid_frames, min(loose_frames, 4)))
        if legacy_score >= score:
            detector = 'imu_legacy_wit_sync'
            support_level = 'candidate_only'
        score = max(score, legacy_score)
        if valid_frames:
            evidence.append(f'legacy WIT 0x55 sync frames with checksum={valid_frames}')
        else:
            evidence.append(f'legacy WIT 0x55 sync headers={loose_frames}')
        evidence.append('current runtime uses WIT Modbus RTU, so passive sniff may stay silent')

    if score <= 0.0:
        return None
    return MatchScore(
        device_type='imu',
        score=min(score, 0.89),
        evidence=tuple(evidence),
        source='dynamic',
        support_level=support_level,
        detector=detector or 'imu_export_csv',
    )


def classify_sample_bytes(sample: bytes) -> list[MatchScore]:
    if not sample:
        return []

    match_map: dict[str, MatchScore] = {}
    text = sample.decode('utf-8', errors='ignore')

    for classifier in (
        lambda: _classify_dvl_sample(text),
        lambda: _classify_volt32_sample(text),
        lambda: _classify_imu_sample(sample, text),
    ):
        match = classifier()
        if match is not None:
            _merge_candidate(match_map, match)

    if USBL_TOKEN_RE.search(text):
        _merge_candidate(
            match_map,
            MatchScore(
                device_type='usbl',
                score=0.60,
                evidence=('contains USBL token',),
                source='dynamic',
                support_level='candidate_only',
                detector='usbl_ascii_token',
            ),
        )

    return sorted(match_map.values(), key=lambda item: item.score, reverse=True)


def choose_baud_candidates(static_matches: Sequence[MatchScore], rules: Sequence[DeviceRule]) -> list[int]:
    by_type = {rule.device_type: rule for rule in rules}
    candidates: list[int] = []
    for match in static_matches:
        rule = by_type.get(match.device_type)
        if rule is None:
            continue
        for baud in rule.baud_candidates:
            if baud not in candidates:
                candidates.append(baud)
    for baud in DEFAULT_DYNAMIC_BAUDS:
        if baud not in candidates:
            candidates.append(baud)
    return candidates


def should_probe_dynamically(identity: dict, static_matches: Sequence[MatchScore], sample_policy: str) -> bool:
    policy = (sample_policy or DEFAULT_SAMPLE_POLICY).strip().lower()
    if policy == 'off':
        return False
    if policy == 'always':
        return True
    if not static_matches:
        return True

    top = static_matches[0]
    second = static_matches[1] if len(static_matches) > 1 else None
    if top.score < 0.75:
        return True
    if second is not None and abs(top.score - second.score) <= AMBIGUOUS_SCORE_DELTA:
        return True

    # 先靠静态身份吃掉大多数稳定设备，只有证据不够时才短时采样，避免 preflight 每次都主动扰动串口。
    return not str(identity.get('path') or '').startswith('/dev/serial/by-id/')


def read_serial_sample(path: str, baud: int, sample_window_s: float, max_bytes: int) -> tuple[Optional[bytes], Optional[str]]:
    try:
        import serial  # type: ignore
    except ImportError as exc:
        return None, f'pyserial unavailable ({exc})'

    try:
        handle = serial.Serial(path, baudrate=baud, timeout=0.10)
    except Exception as exc:  # pragma: no cover - hardware dependent
        return None, str(exc)

    chunks: list[bytes] = []
    collected = 0
    deadline = time.time() + sample_window_s
    try:
        while time.time() < deadline and collected < max_bytes:
            chunk = handle.read(min(256, max_bytes - collected))
            if not chunk:
                time.sleep(0.02)
                continue
            chunks.append(chunk)
            collected += len(chunk)
    finally:  # pragma: no branch - best effort cleanup
        try:
            handle.close()
        except Exception:
            pass
    return b''.join(chunks), None


def probe_dynamic_matches(
    identity: dict,
    static_matches: Sequence[MatchScore],
    rules: Sequence[DeviceRule],
    sample_policy: str,
    sample_window_s: float,
    max_bytes: int,
) -> tuple[list[dict], list[MatchScore], str]:
    if not should_probe_dynamically(identity, static_matches, sample_policy):
        return [], [], 'skipped_static_confident'

    attempts: list[dict] = []
    best_dynamic: list[MatchScore] = []
    for baud in choose_baud_candidates(static_matches, rules):
        sample, error = read_serial_sample(str(identity['path']), baud, sample_window_s, max_bytes)
        if error is not None:
            attempts.append(
                {
                    'baud': baud,
                    'status': 'open_failed',
                    'error': error,
                }
            )
            continue

        sample = sample or b''
        matches = classify_sample_bytes(sample)
        attempts.append(
            {
                'baud': baud,
                'status': 'ok',
                'bytes_read': len(sample),
                'detected_types': [item.device_type for item in matches],
            }
        )
        if matches and (not best_dynamic or matches[0].score > best_dynamic[0].score):
            best_dynamic = matches
        if matches and matches[0].score >= 0.85:
            break

    status = 'sampled' if attempts else 'not_sampled'
    return attempts, best_dynamic, status


def confidence_label(score: float) -> str:
    if score >= 0.85:
        return 'high'
    if score >= MIN_RESOLVE_SCORE:
        return 'medium'
    if score >= 0.35:
        return 'low'
    return 'unknown'


def merge_matches(static_matches: Sequence[MatchScore], dynamic_matches: Sequence[MatchScore]) -> list[MatchScore]:
    merged: dict[str, MatchScore] = {}
    evidence_map: dict[str, list[str]] = {}

    for match in list(static_matches) + list(dynamic_matches):
        existing = merged.get(match.device_type)
        score = match.score
        detector = match.detector
        support_level = match.support_level
        if existing is not None and existing.source != match.source:
            score = min(0.99, max(existing.score, match.score) + 0.12)
            detector = existing.detector if existing.score >= match.score else match.detector
            support_level = _best_support_level(existing.support_level, match.support_level)
        elif existing is not None:
            score = max(existing.score, match.score)
            detector = existing.detector if existing.score >= match.score else match.detector
            support_level = _best_support_level(existing.support_level, match.support_level)

        evidence = evidence_map.setdefault(match.device_type, [])
        for item in match.evidence:
            if item not in evidence:
                evidence.append(item)

        merged[match.device_type] = MatchScore(
            device_type=match.device_type,
            score=score,
            evidence=tuple(evidence),
            source='merged',
            support_level=support_level,
            detector=detector,
        )

    return sorted(merged.values(), key=lambda item: item.score, reverse=True)


def identify_device(
    identity: dict,
    rules: Sequence[DeviceRule],
    *,
    sample_policy: str = DEFAULT_SAMPLE_POLICY,
    sample_window_s: float = DEFAULT_SAMPLE_WINDOW_S,
    max_bytes: int = DEFAULT_MAX_SAMPLE_BYTES,
) -> dict:
    rule_map = {rule.device_type: rule for rule in rules}
    static_matches = [match for match in (score_static_identity(identity, rule) for rule in rules) if match is not None]
    static_matches = sorted(static_matches, key=lambda item: item.score, reverse=True)
    dynamic_attempts, dynamic_matches, dynamic_status = probe_dynamic_matches(
        identity,
        static_matches,
        rules,
        sample_policy,
        sample_window_s,
        max_bytes,
    )
    merged_matches = merge_matches(static_matches, dynamic_matches)

    top = merged_matches[0] if merged_matches else None
    second = merged_matches[1] if len(merged_matches) > 1 else None

    ambiguous = False
    if top is not None and second is not None and top.score >= MIN_RESOLVE_SCORE and second.score >= MIN_RESOLVE_SCORE:
        ambiguous = abs(top.score - second.score) <= AMBIGUOUS_SCORE_DELTA

    if top is None:
        device_type = 'unknown'
        score = 0.0
        match_basis = ['no static identity or dynamic fingerprint matched']
        resolution_reason = 'no_match'
    elif ambiguous:
        device_type = 'unknown'
        score = top.score
        match_basis = list(top.evidence)
        resolution_reason = 'ambiguous_candidates'
    elif top.score < MIN_RESOLVE_SCORE:
        device_type = 'unknown'
        score = top.score
        match_basis = list(top.evidence)
        resolution_reason = 'score_below_floor'
    else:
        device_type = top.device_type
        score = top.score
        match_basis = list(top.evidence)
        resolution_reason = 'resolved'

    recommended_binding = str(identity.get('path') or identity.get('canonical_path') or '')
    if not recommended_binding:
        recommended_binding = str(identity.get('canonical_path') or '')

    top_rule = rule_map.get(top.device_type) if top is not None else None

    risk_hints: list[str] = []
    if not str(identity.get('path') or '').startswith('/dev/serial/by-id/'):
        risk_hints.append('当前不是 by-id 稳定路径，仍有 ttyUSB/ttyACM 跳变风险。')
    if dynamic_status == 'sampled' and dynamic_attempts and all(item['status'] != 'ok' or not item.get('bytes_read') for item in dynamic_attempts):
        risk_hints.append('动态采样未拿到有效字节，当前判断主要依赖静态身份。')
    if top is not None and top.device_type == 'imu' and not dynamic_matches:
        risk_hints.append('当前 IMU runtime 使用 WIT Modbus 轮询；被动采样可能无字节，静态白名单不足时应保持 unknown。')
    if ambiguous:
        risk_hints.append('存在接近分数的候选类型，preflight 应拒绝自动绑定。')
    if resolution_reason == 'score_below_floor' and top is not None:
        risk_hints.append(f'最高分候选是 {top.device_type}，但未达到 {MIN_RESOLVE_SCORE:.2f} 置信度下限。')
    if device_type == 'unknown':
        risk_hints.append('当前设备未形成可信绑定，需要补充规则、现场样本或人工确认。')

    return {
        'device_type': device_type,
        'current_path': str(identity.get('path') or ''),
        'canonical_path': str(identity.get('canonical_path') or ''),
        'tty_name': str(identity.get('tty_name') or ''),
        'static_identity': {
            'by_id_name': str(identity.get('by_id_name') or ''),
            'vendor_id': str(identity.get('vendor_id') or ''),
            'product_id': str(identity.get('product_id') or ''),
            'serial': str(identity.get('serial') or ''),
            'manufacturer': str(identity.get('manufacturer') or ''),
            'product': str(identity.get('product') or ''),
        },
        'static_matches': [serialize_match(match) for match in static_matches],
        'dynamic_probe': {
            'policy': sample_policy,
            'status': dynamic_status,
            'attempts': dynamic_attempts,
            'best_match': serialize_match(dynamic_matches[0] if dynamic_matches else None),
        },
        'match_basis': match_basis,
        'confidence': {
            'score': round(score, 3),
            'label': confidence_label(score),
            'resolve_floor': MIN_RESOLVE_SCORE,
        },
        'resolution': {
            'resolved': resolution_reason == 'resolved',
            'reason': resolution_reason,
            'score_floor': MIN_RESOLVE_SCORE,
            'top_candidate': serialize_match(top),
        },
        'rule_support': {
            'static_identity': top_rule.static_support if top_rule is not None else 'unknown',
            'dynamic_probe': top_rule.dynamic_support if top_rule is not None else 'unknown',
            'static_fields': serialize_static_field_support(top_rule) if top_rule is not None else {},
            'sample_gaps': {
                'static_identity': list(top_rule.static_sample_gaps) if top_rule is not None else [],
                'dynamic_probe': list(top_rule.dynamic_sample_gaps) if top_rule is not None else [],
            },
            'notes': list(top_rule.notes) if top_rule is not None else [],
        },
        'ambiguous': ambiguous,
        'ambiguous_with': [
            match.device_type
            for match in merged_matches[1:]
            if top is not None and match.score >= MIN_RESOLVE_SCORE and abs(top.score - match.score) <= AMBIGUOUS_SCORE_DELTA
        ],
        'recommended_binding': recommended_binding,
        'risk_hints': risk_hints,
        'candidate_scores': [serialize_match(match) for match in merged_matches],
    }


def summarize_devices(devices: Sequence[dict]) -> str:
    if not devices:
        return 'no serial candidates discovered'
    parts = []
    for item in devices:
        reason = item.get('resolution', {}).get('reason', 'unknown')
        parts.append(
            f"{item['device_type']}@{item['tty_name'] or item['current_path']}"
            f"(score={item['confidence']['score']}, ambiguous={str(item['ambiguous']).lower()}, reason={reason})"
        )
    return '; '.join(parts)


def scan_device_inventory(
    *,
    dev_root: pathlib.Path = pathlib.Path('/dev'),
    sys_root: pathlib.Path = pathlib.Path('/sys/class/tty'),
    rules_path: pathlib.Path | None = None,
    sample_policy: str = DEFAULT_SAMPLE_POLICY,
    sample_window_s: float = DEFAULT_SAMPLE_WINDOW_S,
    max_sample_bytes: int = DEFAULT_MAX_SAMPLE_BYTES,
    requested_startup_profile: str = device_profiles.AUTO_PROFILE,
) -> dict:
    rules = load_rules(rules_path)
    rule_catalog = serialize_rule_catalog(rules)
    identities = scan_serial_snapshot(dev_root, sys_root)
    devices = [
        identify_device(
            identity,
            rules,
            sample_policy=sample_policy,
            sample_window_s=sample_window_s,
            max_bytes=max_sample_bytes,
        )
        for identity in identities
    ]

    counts = device_profiles.count_device_types(devices)
    recommended_profile = device_profiles.recommend_startup_profile(counts)
    selected_profile = device_profiles.resolve_startup_profile(requested_startup_profile, counts)

    recommended_bindings: dict[str, str] = {}
    best_scores: dict[str, float] = {}
    ambiguous_devices = []
    duplicate_types: dict[str, int] = {}
    for item in devices:
        device_type = item['device_type'] if not item['ambiguous'] else 'unknown'
        duplicate_types[device_type] = duplicate_types.get(device_type, 0) + 1
        if item['ambiguous']:
            ambiguous_devices.append(item['current_path'])
            continue
        score = float(item['confidence']['score'])
        if device_type == 'unknown':
            continue
        if score > best_scores.get(device_type, -1.0):
            best_scores[device_type] = score
            recommended_bindings[device_type] = item['recommended_binding']

    risk_hints: list[str] = []
    if ambiguous_devices:
        risk_hints.append('存在歧义设备，supervisor/preflight 应拒绝自动绑定并要求人工确认。')
    for device_type in ('imu', 'volt32', 'dvl', 'usbl'):
        if duplicate_types.get(device_type, 0) > 1:
            risk_hints.append(f'发现多个 {device_type} 候选，推荐绑定只保留最高分路径，仍需人工复核。')
    unknown_count = int(counts.get('unknown', 0) or 0)
    if unknown_count:
        risk_hints.append(f'有 {unknown_count} 个串口候选未达到置信度下限，不参与 startup profile 推荐。')

    return {
        'generated_wall_time': wall_time_now(),
        'rules_path': str((rules_path or DEFAULT_RULES_PATH).resolve()),
        'sample_policy': sample_policy,
        'sample_window_s': sample_window_s,
        'max_sample_bytes': max_sample_bytes,
        'requested_startup_profile': requested_startup_profile,
        'devices': devices,
        'device_counts': counts,
        'device_summary': summarize_devices(devices),
        'rule_catalog': rule_catalog,
        'rule_maturity_summary': summarize_rule_catalog(rule_catalog),
        'static_sample_gap_summary': summarize_static_sample_gaps(rule_catalog),
        'recommended_bindings': recommended_bindings,
        'ambiguous': bool(ambiguous_devices),
        'ambiguous_devices': ambiguous_devices,
        'risk_hints': risk_hints,
        'recommended_startup_profile': recommended_profile,
        'selected_startup_profile': selected_profile,
    }


def print_table(summary: dict) -> None:
    devices = summary.get('devices', [])
    if not devices:
        print('no serial devices discovered')
    else:
        print('device_type,current_path,confidence,ambiguous,resolution_reason,recommended_binding,match_basis')
        for item in devices:
            match_basis = '|'.join(item['match_basis'])
            print(
                ','.join(
                    [
                        item['device_type'],
                        item['current_path'],
                        str(item['confidence']['score']),
                        str(item['ambiguous']).lower(),
                        item['resolution']['reason'],
                        item['recommended_binding'],
                        match_basis,
                    ]
                )
            )

    selected = summary['selected_startup_profile']
    print('')
    print(f"recommended_startup_profile={summary['recommended_startup_profile']['profile']}")
    print(f"selected_startup_profile={selected['selected']}")
    print(f"launch_mode={selected['launch_mode']}")
    print(f"device_counts={device_profiles.summarize_device_counts(summary['device_counts'])}")
    if summary.get('rule_maturity_summary'):
        print(f"rule_maturity={summary['rule_maturity_summary']}")
    if summary.get('static_sample_gap_summary'):
        print(f"static_sample_gaps={summary['static_sample_gap_summary']}")
    if summary['risk_hints']:
        print('risk_hints=')
        for item in summary['risk_hints']:
            print(f'  - {item}')


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Serial device identification helper for startup/preflight.')
    parser.add_argument('--dev-root', type=pathlib.Path, default=pathlib.Path('/dev'))
    parser.add_argument('--sys-root', type=pathlib.Path, default=pathlib.Path('/sys/class/tty'))
    parser.add_argument('--rules-path', type=pathlib.Path, default=DEFAULT_RULES_PATH)
    parser.add_argument('--sample-policy', choices=['auto', 'off', 'always'], default=DEFAULT_SAMPLE_POLICY)
    parser.add_argument('--sample-window-s', type=float, default=DEFAULT_SAMPLE_WINDOW_S)
    parser.add_argument('--max-sample-bytes', type=int, default=DEFAULT_MAX_SAMPLE_BYTES)
    parser.add_argument('--startup-profile', default=device_profiles.AUTO_PROFILE)
    parser.add_argument('--json', action='store_true')
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not args.dev_root.exists():
        raise SystemExit(f'dev root not found: {args.dev_root}')
    if not args.sys_root.exists():
        raise SystemExit(f'sys root not found: {args.sys_root}')

    summary = scan_device_inventory(
        dev_root=args.dev_root,
        sys_root=args.sys_root,
        rules_path=args.rules_path,
        sample_policy=args.sample_policy,
        sample_window_s=args.sample_window_s,
        max_sample_bytes=max(1, int(args.max_sample_bytes)),
        requested_startup_profile=args.startup_profile,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_table(summary)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
