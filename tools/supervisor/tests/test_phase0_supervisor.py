from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tools.supervisor import phase0_supervisor as sup


SCRIPT = Path(sup.__file__).resolve()


class Phase0SupervisorTest(unittest.TestCase):
    def wait_for_manifest(self, run_root: Path, timeout_s: float = 5.0) -> Path:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            manifests = list(run_root.rglob('run_manifest.json'))
            if manifests:
                return manifests[0]
            time.sleep(0.1)
        self.fail('timed out waiting for run_manifest.json')

    def wait_for_state(self, status_path: Path, target_state: str, timeout_s: float = 8.0) -> dict:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if status_path.exists():
                data = json.loads(status_path.read_text(encoding='utf-8'))
                if data.get('supervisor_state') == target_state:
                    return data
            time.sleep(0.1)
        self.fail(f'timed out waiting for supervisor_state={target_state}')

    def test_extract_device_paths_from_text(self) -> None:
        config_text = '\n'.join(
            [
                'imu:',
                '  driver:',
                '    port: "/dev/ttyUSB0"',
                'dvl:',
                '  driver:',
                '    port: "/dev/ttyACM0"',
                'extra:',
                '  port: "/dev/ttyUSB0"',
            ]
        )
        self.assertEqual(['/dev/ttyUSB0', '/dev/ttyACM0'], sup.extract_device_paths_from_text(config_text))

    def test_bench_profile_preflight_paths_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = sup.build_profile('bench')
            results = sup.run_preflight_checks(profile, Path(tmpdir), skip_port_check=True)
            failure_titles = [item.title for item in results if not item.ok]
            unexpected = [title for title in failure_titles if not title.startswith('bench_device_')]
            self.assertEqual([], unexpected)
            self.assertTrue(any(item.title == 'uwnav_navd_binary' and item.ok for item in results))

    def test_mock_profile_preflight_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = [
                sys.executable,
                str(SCRIPT),
                'preflight',
                '--profile', 'mock',
                '--run-root', str(Path(tmpdir)),
                '--skip-port-check',
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.assertEqual(0, res.returncode, res.stderr or res.stdout)
            self.assertIn('Phase0 Supervisor Preflight (mock)', res.stdout)

    def test_mock_profile_detached_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)
            start_cmd = [
                sys.executable,
                str(SCRIPT),
                'start',
                '--profile', 'mock',
                '--detach',
                '--run-root', str(run_root),
                '--start-settle-s', '0.1',
                '--poll-interval-s', '0.1',
                '--stop-timeout-s', '2.0',
            ]
            start_res = subprocess.run(start_cmd, capture_output=True, text=True, check=False)
            self.assertEqual(0, start_res.returncode, start_res.stderr or start_res.stdout)

            manifest_path = self.wait_for_manifest(run_root)
            run_dir = manifest_path.parent
            status_path = run_dir / 'process_status.json'
            fault_path = run_dir / 'last_fault_summary.txt'
            events_path = run_dir / 'supervisor_events.csv'

            self.assertTrue(status_path.exists())
            self.assertTrue(fault_path.exists())
            self.assertTrue(events_path.exists())

            status_cmd = [
                sys.executable,
                str(SCRIPT),
                'status',
                '--run-root', str(run_root),
                '--json',
            ]
            status_res = subprocess.run(status_cmd, capture_output=True, text=True, check=False)
            self.assertEqual(0, status_res.returncode, status_res.stderr)
            status_data = json.loads(status_res.stdout)
            self.assertEqual('mock', status_data['profile'])

            stop_cmd = [
                sys.executable,
                str(SCRIPT),
                'stop',
                '--run-root', str(run_root),
                '--timeout-s', '5.0',
            ]
            stop_res = subprocess.run(stop_cmd, capture_output=True, text=True, check=False)
            self.assertEqual(0, stop_res.returncode, stop_res.stderr or stop_res.stdout)

            final_status = self.wait_for_state(status_path, 'stopped')
            process_states = {item['name']: item['state'] for item in final_status['processes']}
            self.assertEqual({'stopped'}, set(process_states.values()))


if __name__ == '__main__':
    unittest.main()
