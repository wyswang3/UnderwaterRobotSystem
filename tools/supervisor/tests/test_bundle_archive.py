from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from tools.supervisor import bundle_archive


SCRIPT = Path(bundle_archive.__file__).resolve()


def write_minimal_bundle(bundle_dir: Path, *, run_id: str, stage: str = 'child_process_started') -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / 'supervisor').mkdir(parents=True, exist_ok=True)
    (bundle_dir / 'bundle_summary.json').write_text(
        json.dumps(
            {
                'run_id': run_id,
                'profile': 'bench',
                'bundle_status': 'incomplete',
                'run_stage': stage,
                'bundle_dir': str(bundle_dir),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    (bundle_dir / 'bundle_summary.txt').write_text('bundle_status=incomplete\n', encoding='utf-8')
    (bundle_dir / 'supervisor' / 'run_manifest.json').write_text('{"run_id": "x"}\n', encoding='utf-8')


class BundleArchiveTest(unittest.TestCase):
    def test_archive_bundle_dir_creates_tar_gz(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_dir = Path(tmpdir) / '20260326_202046'
            write_minimal_bundle(bundle_dir, run_id='20260326_201943_37835')

            summary = bundle_archive.archive_bundle_dir(bundle_dir)
            archive_path = Path(summary['archive_path'])

            self.assertTrue(archive_path.exists())
            self.assertEqual('tar.gz', summary['archive_format'])
            self.assertGreater(summary['archive_size_bytes'], 0)

            with tarfile.open(archive_path, mode='r:gz') as tar:
                names = tar.getnames()

            self.assertIn(f'{bundle_dir.name}/bundle_summary.json', names)
            self.assertIn(f'{bundle_dir.name}/supervisor/run_manifest.json', names)

    def test_cli_uses_latest_bundle_under_run_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / '2026-03-26' / '20260326_201943_37835'
            old_bundle = run_dir / 'bundle' / '20260326_202000'
            new_bundle = run_dir / 'bundle' / '20260326_202046'
            write_minimal_bundle(old_bundle, run_id='old')
            write_minimal_bundle(new_bundle, run_id='new', stage='preflight_failed_before_spawn')

            old_ts = 1711455600
            new_ts = old_ts + 60
            os.utime(old_bundle, (old_ts, old_ts))
            os.utime(old_bundle / 'bundle_summary.json', (old_ts, old_ts))
            os.utime(new_bundle, (new_ts, new_ts))
            os.utime(new_bundle / 'bundle_summary.json', (new_ts, new_ts))

            cmd = [
                sys.executable,
                str(SCRIPT),
                '--run-dir',
                str(run_dir),
                '--json',
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)

            self.assertEqual(0, res.returncode, res.stderr or res.stdout)
            summary = json.loads(res.stdout)
            self.assertEqual(str(new_bundle), summary['bundle_dir'])
            self.assertEqual('preflight_failed_before_spawn', summary['run_stage'])
            self.assertTrue(Path(summary['archive_path']).exists())


if __name__ == '__main__':
    unittest.main()
