from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.supervisor import device_identification as ident
from tools.supervisor import device_profiles
from tools.supervisor import phase0_supervisor as sup


SCRIPT = Path(sup.__file__).resolve()
FIXTURE_DIR = Path(__file__).resolve().parent / 'fixtures'


def read_fixture_bytes(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


def build_real_valued_volt_line_sample() -> bytes:
    text = (FIXTURE_DIR / 'volt32_export_excerpt.csv').read_text(encoding='utf-8')
    reader = csv.DictReader(io.StringIO(text))
    row = next(reader)
    lines = [f'{key}: {value}' for key, value in row.items() if key.startswith('CH')]
    return ('\n'.join(lines) + '\n').encode('utf-8')


class DeviceIdentificationTests(unittest.TestCase):
    def test_scan_prefers_by_id_and_recommends_imu_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix='device_ident_') as td:
            root = Path(td)
            dev_root = root / 'dev'
            sys_root = root / 'sys' / 'class' / 'tty'
            (dev_root / 'serial' / 'by-id').mkdir(parents=True)
            (sys_root / 'ttyUSB9' / 'device').mkdir(parents=True)
            (dev_root / 'ttyUSB9').touch()
            (dev_root / 'serial' / 'by-id' / 'usb-imu-main').symlink_to(dev_root / 'ttyUSB9')
            (sys_root / 'ttyUSB9' / 'device' / 'idVendor').write_text('10C4\n', encoding='utf-8')
            (sys_root / 'ttyUSB9' / 'device' / 'idProduct').write_text('EA60\n', encoding='utf-8')
            (sys_root / 'ttyUSB9' / 'device' / 'serial').write_text('imu-001\n', encoding='utf-8')
            (sys_root / 'ttyUSB9' / 'device' / 'manufacturer').write_text('WIT\n', encoding='utf-8')
            (sys_root / 'ttyUSB9' / 'device' / 'product').write_text('WIT-IMU\n', encoding='utf-8')

            summary = ident.scan_device_inventory(
                dev_root=dev_root,
                sys_root=sys_root,
                sample_policy='off',
            )
            self.assertEqual(1, len(summary['devices']))
            self.assertEqual('imu', summary['devices'][0]['device_type'])
            self.assertEqual('resolved', summary['devices'][0]['resolution']['reason'])
            self.assertEqual('imu_only', summary['recommended_startup_profile']['profile'])
            self.assertEqual(str(dev_root / 'serial' / 'by-id' / 'usb-imu-main'), summary['recommended_bindings']['imu'])

    def test_real_imu_export_sample_classifies_as_imu(self) -> None:
        matches = ident.classify_sample_bytes(read_fixture_bytes('imu_export_excerpt.csv'))
        self.assertTrue(matches)
        self.assertEqual('imu', matches[0].device_type)
        self.assertGreaterEqual(matches[0].score, 0.8)
        self.assertEqual('sample_backed', matches[0].support_level)
        self.assertIn('Acc/As/H/Ang axes all present', ' '.join(matches[0].evidence))

    def test_real_volt32_export_sample_classifies_as_volt32(self) -> None:
        matches = ident.classify_sample_bytes(read_fixture_bytes('volt32_export_excerpt.csv'))
        self.assertTrue(matches)
        self.assertEqual('volt32', matches[0].device_type)
        self.assertGreaterEqual(matches[0].score, 0.8)
        self.assertIn('CH0..CH15', ' '.join(matches[0].evidence))

    def test_real_dvl_raw_sample_classifies_as_dvl(self) -> None:
        matches = ident.classify_sample_bytes(read_fixture_bytes('dvl_rawline_excerpt.csv'))
        self.assertTrue(matches)
        self.assertEqual('dvl', matches[0].device_type)
        self.assertGreaterEqual(matches[0].score, 0.85)
        self.assertEqual('sample_backed', matches[0].support_level)
        self.assertIn('DVL reply tokens', ' '.join(matches[0].evidence))

    def test_unknown_sample_remains_unknown(self) -> None:
        matches = ident.classify_sample_bytes(read_fixture_bytes('unknown_serial_excerpt.txt'))
        self.assertEqual([], matches)

    def test_mixed_real_samples_become_ambiguous(self) -> None:
        identity = {
            'path': '/dev/ttyUSB7',
            'canonical_path': '/dev/ttyUSB7',
            'tty_name': 'ttyUSB7',
            'by_id_name': '',
            'vendor_id': '',
            'product_id': '',
            'serial': '',
            'manufacturer': '',
            'product': '',
        }
        mixed_sample = read_fixture_bytes('dvl_rawline_excerpt.csv') + b'\n' + build_real_valued_volt_line_sample()
        with mock.patch.object(ident, 'read_serial_sample', return_value=(mixed_sample, None)):
            device = ident.identify_device(
                identity,
                ident.load_rules(),
                sample_policy='always',
            )
        self.assertEqual('unknown', device['device_type'])
        self.assertTrue(device['ambiguous'])
        self.assertIn('dvl', [item['device_type'] for item in device['candidate_scores']])
        self.assertIn('volt32', [item['device_type'] for item in device['candidate_scores']])

    def test_sample_backed_profile_recommendation_reaches_imu_dvl(self) -> None:
        imu_match = ident.classify_sample_bytes(read_fixture_bytes('imu_export_excerpt.csv'))[0]
        dvl_match = ident.classify_sample_bytes(read_fixture_bytes('dvl_rawline_excerpt.csv'))[0]
        counts = device_profiles.count_device_types(
            [
                {'device_type': imu_match.device_type, 'ambiguous': False},
                {'device_type': dvl_match.device_type, 'ambiguous': False},
            ]
        )
        resolved = device_profiles.recommend_startup_profile(counts)
        self.assertEqual('imu_dvl', resolved['profile'])

    def test_profile_resolution_marks_reserved_profile(self) -> None:
        counts = device_profiles.count_device_types(['imu', 'dvl', 'usbl'])
        resolved = device_profiles.resolve_startup_profile('imu_dvl_usbl', counts)
        self.assertEqual('imu_dvl_usbl', resolved['selected'])
        self.assertEqual('reserved', resolved['launch_mode'])
        self.assertTrue(resolved['warnings'])

    def test_supervisor_manifest_includes_device_identification_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix='phase0_ctx_') as td:
            run_root = Path(td) / 'runs'
            run_dir = run_root / '2026-03-26' / '20260326_220000_1234'
            profile = sup.build_profile('mock')
            ctx = sup.init_run_context(profile, run_root, run_dir, sup.OUTPUT_CAPTURE, 0.1, 1.0, 5)
            ctx.startup_profile_name = 'imu_only'
            ctx.startup_profile_source = 'auto'
            ctx.recommended_startup_profile_name = 'imu_only'
            ctx.device_identification_summary = {
                'device_counts': {'imu': 1, 'dvl': 0, 'usbl': 0, 'volt32': 0, 'unknown': 0},
                'devices': [{'device_type': 'imu', 'current_path': '/dev/serial/by-id/usb-imu-main'}],
            }

            manifest = sup.build_manifest(ctx)
            status = sup.build_process_status(ctx)
            self.assertEqual('imu_only', manifest['startup_profile'])
            self.assertEqual('imu_only', status['startup_profile'])
            self.assertIn('device_identification', manifest)
            self.assertEqual(1, manifest['device_identification']['device_counts']['imu'])

    def test_device_scan_cli_emits_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix='device_ident_cli_') as td:
            root = Path(td)
            dev_root = root / 'dev'
            sys_root = root / 'sys' / 'class' / 'tty'
            (dev_root / 'serial' / 'by-id').mkdir(parents=True)
            (sys_root / 'ttyUSB3' / 'device').mkdir(parents=True)
            (dev_root / 'ttyUSB3').touch()
            (dev_root / 'serial' / 'by-id' / 'usb-imu-main').symlink_to(dev_root / 'ttyUSB3')
            (sys_root / 'ttyUSB3' / 'device' / 'idVendor').write_text('10C4\n', encoding='utf-8')
            (sys_root / 'ttyUSB3' / 'device' / 'idProduct').write_text('EA60\n', encoding='utf-8')
            (sys_root / 'ttyUSB3' / 'device' / 'serial').write_text('imu-002\n', encoding='utf-8')

            cmd = [
                sys.executable,
                str(SCRIPT),
                'device-scan',
                '--dev-root', str(dev_root),
                '--sys-root', str(sys_root),
                '--sample-policy', 'off',
                '--json',
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.assertEqual(0, res.returncode, res.stderr or res.stdout)
            payload = json.loads(res.stdout)
            self.assertEqual('imu_only', payload['recommended_startup_profile']['profile'])
            self.assertEqual('imu', payload['devices'][0]['device_type'])


if __name__ == '__main__':
    unittest.main()
