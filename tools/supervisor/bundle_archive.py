#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import tarfile
from pathlib import Path
from typing import Optional

DEFAULT_RUN_ROOT = Path('/tmp/phase0_supervisor_runs')


class BundleArchiveError(RuntimeError):
    pass


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def discover_latest_run_dir(run_root: Path) -> Optional[Path]:
    if not run_root.exists():
        return None
    manifests = sorted(run_root.rglob('run_manifest.json'), key=lambda path: path.stat().st_mtime)
    if not manifests:
        return None
    return manifests[-1].parent


def discover_latest_bundle_dir(run_dir: Path) -> Optional[Path]:
    bundle_root = run_dir / 'bundle'
    if not bundle_root.exists() or not bundle_root.is_dir():
        return None

    bundle_dirs = sorted(
        (
            path
            for path in bundle_root.iterdir()
            if path.is_dir() and (path / 'bundle_summary.json').exists()
        ),
        key=lambda path: path.stat().st_mtime,
    )
    if not bundle_dirs:
        return None
    return bundle_dirs[-1]


def resolve_target_bundle_dir(
    *,
    run_root: Path,
    run_dir: Optional[Path],
    bundle_dir: Optional[Path],
) -> Path:
    if bundle_dir is not None:
        target = bundle_dir.resolve()
    else:
        target_run_dir = run_dir.resolve() if run_dir is not None else discover_latest_run_dir(run_root.resolve())
        if target_run_dir is None:
            raise BundleArchiveError(f'no supervisor run found under {run_root}')
        target = discover_latest_bundle_dir(target_run_dir)
        if target is None:
            raise BundleArchiveError(f'no bundle export found under {target_run_dir / "bundle"}')

    if not target.exists():
        raise BundleArchiveError(f'bundle directory does not exist: {target}')
    if not target.is_dir():
        raise BundleArchiveError(f'not a directory: {target}')
    if not (target / 'bundle_summary.json').exists():
        raise BundleArchiveError(f'missing bundle summary: {target / "bundle_summary.json"}')
    return target


def default_archive_path(bundle_dir: Path) -> Path:
    return bundle_dir.with_suffix('.tar.gz')


def count_files_and_bytes(bundle_dir: Path) -> tuple[int, int]:
    file_count = 0
    total_bytes = 0
    for path in bundle_dir.rglob('*'):
        if not path.is_file():
            continue
        file_count += 1
        total_bytes += path.stat().st_size
    return file_count, total_bytes


def archive_bundle_dir(bundle_dir: Path, *, output_path: Optional[Path] = None) -> dict:
    bundle_dir = bundle_dir.resolve()
    summary = load_json(bundle_dir / 'bundle_summary.json')

    archive_path = output_path.resolve() if output_path is not None else default_archive_path(bundle_dir)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = archive_path.with_name(archive_path.name + '.tmp')

    with tarfile.open(tmp_path, mode='w:gz') as tar:
        tar.add(bundle_dir, arcname=bundle_dir.name)

    tmp_path.replace(archive_path)

    file_count, payload_bytes = count_files_and_bytes(bundle_dir)
    archive_size_bytes = archive_path.stat().st_size
    return {
        'run_id': summary.get('run_id'),
        'profile': summary.get('profile'),
        'bundle_dir': str(bundle_dir),
        'archive_path': str(archive_path),
        'archive_format': 'tar.gz',
        'bundle_status': summary.get('bundle_status'),
        'run_stage': summary.get('run_stage'),
        'file_count': file_count,
        'payload_bytes': payload_bytes,
        'archive_size_bytes': archive_size_bytes,
    }


def cmd_main(args: argparse.Namespace) -> int:
    try:
        bundle_dir = resolve_target_bundle_dir(
            run_root=args.run_root,
            run_dir=args.run_dir,
            bundle_dir=args.bundle_dir,
        )
        summary = archive_bundle_dir(bundle_dir, output_path=args.output)
    except BundleArchiveError as exc:
        print(f'[ERR] {exc}')
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    print(f"[INFO] bundle_dir={summary['bundle_dir']}")
    print(f"[INFO] archive_path={summary['archive_path']}")
    print(f"[INFO] archive_format={summary['archive_format']}")
    print(f"[INFO] run_id={summary['run_id']}")
    print(f"[INFO] bundle_status={summary['bundle_status']}")
    print(f"[INFO] run_stage={summary['run_stage']}")
    print(f"[INFO] file_count={summary['file_count']}")
    print(f"[INFO] payload_bytes={summary['payload_bytes']}")
    print(f"[INFO] archive_size_bytes={summary['archive_size_bytes']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Create a minimal tar.gz archive from an exported incident bundle.')
    parser.add_argument('--run-root', type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--bundle-dir', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--json', action='store_true')
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    return cmd_main(args)


if __name__ == '__main__':
    raise SystemExit(main())
