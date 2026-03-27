from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from tools.supervisor import incident_bundle
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

    def test_control_only_profile_preflight_paths_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = sup.build_profile('control_only')
            results = sup.run_preflight_checks(profile, Path(tmpdir), skip_port_check=True, enable_device_scan=True)
            failure_titles = [item.title for item in results if not item.ok]
            self.assertEqual([], failure_titles)
            self.assertTrue(any(item.title == 'pwm_control_program_binary' and item.ok for item in results))
            self.assertTrue(any(item.title == 'gcs_server_binary' and item.ok for item in results))
            gate = next(item for item in results if item.title == 'startup_profile_gate')
            self.assertIn('navigation is optional', gate.detail)

    def test_control_only_device_scan_ambiguity_is_warning_only(self) -> None:
        summary = sup.build_empty_device_scan_summary('auto')
        summary['ambiguous'] = True
        summary['ambiguous_devices'] = ['ttyUSB0']

        results = sup.build_device_scan_preflight_results(sup.build_profile('control_only'), summary)
        ambiguity = next(item for item in results if item.title == 'device_binding_ambiguity')
        gate = next(item for item in results if item.title == 'startup_profile_gate')

        self.assertTrue(ambiguity.ok)
        self.assertIn('continue with control + comm only', ambiguity.detail)
        self.assertTrue(gate.ok)

    def test_empty_device_scan_summary_exposes_rule_maturity_lines(self) -> None:
        summary = sup.build_empty_device_scan_summary('auto')
        results = sup.build_device_scan_preflight_results(sup.build_profile('bench'), summary)
        titles = [item.title for item in results]
        self.assertIn('device_rule_maturity', titles)
        self.assertIn('device_static_sample_gaps', titles)

    def test_control_only_capability_stays_runtime_safe_when_imu_is_detected(self) -> None:
        summary = sup.build_empty_device_scan_summary('auto')
        summary['device_counts']['imu'] = 1
        summary['selected_startup_profile'] = {
            'selected': 'imu_only',
            'source': 'auto',
            'launch_mode': 'bench_safe_smoke',
            'navigation_requirement': 'required',
            'runtime_level_hint': 'control_nav_optional',
        }
        results = sup.build_device_scan_preflight_results(sup.build_profile('control_only'), summary)
        capability = next(item for item in results if item.title == 'capability_level')

        self.assertIn('active=control_only', capability.detail)
        self.assertIn('device_ready=attitude_feedback', capability.detail)

    def test_sensor_inventory_marks_imu_required_and_dvl_optional(self) -> None:
        summary = sup.build_empty_device_scan_summary('auto')
        inventory = sup.build_sensor_inventory_status(summary, {'level': 'control_only'})

        self.assertEqual('not_present', inventory['imu']['state'])
        self.assertIn('control_only', inventory['imu']['note'])
        self.assertEqual('optional_missing', inventory['dvl']['state'])
        self.assertIn('teleop primary lane 可继续', inventory['dvl']['note'])
        self.assertEqual('device_scan_inventory', inventory['volt32']['visibility'])

    def test_motion_info_status_reads_latest_control_loop_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ctrl_logs = root / 'ctrl' / 'logs' / 'control'
            ctrl_logs.mkdir(parents=True)
            control_log = ctrl_logs / 'control_loop_20260327_210000.csv'
            control_log.write_text(
                '\n'.join([
                    'mono_ns,nav_roll,nav_pitch,nav_yaw,vel_norm,nav_x,nav_y,nav_z',
                    '1,0.1,0.2,0.3,0.4,1.0,2.0,3.0',
                ]),
                encoding='utf-8',
            )
            manifest = {
                'created_wall_time': datetime.now().astimezone().isoformat(timespec='seconds'),
                'processes': [
                    {'name': 'pwm_control_program', 'cwd': str(root / 'ctrl'), 'required_paths': []},
                ],
            }
            capability = {
                'level': 'relative_nav',
                'expected_motion_fields': ['roll', 'pitch', 'yaw', 'velocity', 'relative_position'],
            }

            motion = sup.build_motion_info_status(manifest, capability)

            self.assertEqual('available', motion['state'])
            self.assertEqual('0.1', motion['values']['roll'])
            self.assertEqual('0.4', motion['values']['velocity'])
            self.assertIn('nav_x=1.0', motion['values']['relative_position'])

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
            self.assertIn('child_output=capture', start_res.stdout)

            manifest_path = self.wait_for_manifest(run_root)
            run_dir = manifest_path.parent
            status_path = run_dir / 'process_status.json'
            fault_path = run_dir / 'last_fault_summary.txt'
            events_path = run_dir / 'supervisor_events.csv'

            self.assertTrue(status_path.exists())
            self.assertTrue(fault_path.exists())
            self.assertTrue(events_path.exists())

            manifest_data = json.loads(manifest_path.read_text(encoding='utf-8'))
            self.assertEqual('capture', manifest_data['child_output_mode'])
            self.assertTrue((run_dir / 'child_logs').exists())
            for proc in manifest_data['processes']:
                self.assertTrue(proc['log_files']['stdout'].endswith('stdout.log'))
                self.assertTrue(proc['log_files']['stderr'].endswith('stderr.log'))
                self.assertTrue(Path(proc['log_files']['stdout']).exists())
                self.assertTrue(Path(proc['log_files']['stderr']).exists())

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
            self.assertEqual('capture', status_data['child_output_mode'])

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


    def test_bundle_command_marks_missing_runtime_logs_for_mock_run(self) -> None:
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

            stop_cmd = [
                sys.executable,
                str(SCRIPT),
                'stop',
                '--run-root', str(run_root),
                '--timeout-s', '5.0',
            ]
            stop_res = subprocess.run(stop_cmd, capture_output=True, text=True, check=False)
            self.assertEqual(0, stop_res.returncode, stop_res.stderr or stop_res.stdout)

            bundle_cmd = [
                sys.executable,
                str(SCRIPT),
                'bundle',
                '--run-root', str(run_root),
                '--json',
            ]
            bundle_res = subprocess.run(bundle_cmd, capture_output=True, text=True, check=False)
            self.assertEqual(0, bundle_res.returncode, bundle_res.stderr or bundle_res.stdout)
            summary = json.loads(bundle_res.stdout)
            self.assertTrue(summary['bundle_export_ok'])
            self.assertTrue(summary['bundle_incomplete'])
            self.assertEqual('child_process_stopped_after_start', summary['run_stage'])
            self.assertTrue(summary['required_ok'])
            self.assertIn('nav.nav_timing', summary['missing_optional_keys'])
            self.assertTrue(any('optional artifacts 缺失' in item for item in summary['triage_hints']))
            bundle_dir = Path(summary['bundle_dir'])
            self.assertTrue((bundle_dir / 'bundle_summary.json').exists())
            self.assertTrue((bundle_dir / 'bundle_summary.txt').exists())
            self.assertTrue((bundle_dir / 'supervisor' / 'run_manifest.json').exists())
            self.assertTrue((bundle_dir / 'child_logs' / 'uwnav_navd' / 'stdout.log').exists())
            self.assertEqual(run_dir, bundle_dir.parents[1])



    def test_bundle_export_marks_preflight_failed_stage_before_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / 'reports' / 'supervisor_runs' / '2026-03-26' / '20260326_140000_6789'
            child_dir = run_dir / 'child_logs' / 'uwnav_navd'
            child_dir.mkdir(parents=True)
            (child_dir / 'stdout.log').write_text('', encoding='utf-8')
            (child_dir / 'stderr.log').write_text('', encoding='utf-8')

            manifest = {
                'run_id': '20260326_140000_6789',
                'profile': 'bench',
                'created_wall_time': '2026-03-26T14:00:00+08:00',
                'processes': [
                    {
                        'name': 'uwnav_navd',
                        'cwd': str(root / 'nav_core'),
                        'required_paths': [],
                        'log_files': {
                            'stdout': str(child_dir / 'stdout.log'),
                            'stderr': str(child_dir / 'stderr.log'),
                        },
                    }
                ],
            }
            status = {
                'run_id': manifest['run_id'],
                'profile': 'bench',
                'supervisor_state': 'failed',
                'last_fault_event': 'preflight_failed',
                'processes': [
                    {
                        'name': 'uwnav_navd',
                        'state': 'not_started',
                    }
                ],
            }
            (run_dir / 'run_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            (run_dir / 'process_status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
            (run_dir / 'last_fault_summary.txt').write_text('event=preflight_failed\n', encoding='utf-8')
            (run_dir / 'supervisor_events.csv').write_text('mono_ns,event\n1,preflight_failed\n', encoding='utf-8')

            summary = incident_bundle.export_run_bundle(run_dir)
            self.assertEqual('preflight_failed_before_spawn', summary['run_stage'])
            self.assertEqual('preflight_failed', summary['last_fault_event'])
            self.assertTrue(any('零字节 child logs' in item for item in summary['triage_hints']))

    def test_bundle_export_marks_missing_required_supervisor_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / 'reports' / 'supervisor_runs' / '2026-03-26' / '20260326_130000_5678'
            run_dir.mkdir(parents=True)

            manifest = {
                'run_id': '20260326_130000_5678',
                'profile': 'mock',
                'created_wall_time': '2026-03-26T13:00:00+08:00',
                'processes': [],
            }
            (run_dir / 'run_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

            summary = incident_bundle.export_run_bundle(run_dir)
            self.assertTrue(summary['bundle_incomplete'])
            self.assertFalse(summary['required_ok'])
            self.assertIn('supervisor.process_status', summary['missing_required_keys'])
            self.assertIn('supervisor.last_fault_summary', summary['missing_required_keys'])
            self.assertIn('supervisor.supervisor_events', summary['missing_required_keys'])
            bundle_dir = Path(summary['bundle_dir'])
            self.assertTrue((bundle_dir / 'bundle_summary.json').exists())
            self.assertTrue((bundle_dir / 'bundle_summary.txt').exists())

    def test_bundle_export_collects_runtime_logs_from_manifest_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / 'reports' / 'supervisor_runs' / '2026-03-26' / '20260326_120000_1234'
            run_dir.mkdir(parents=True)

            nav_cfg = root / 'nav_core' / 'config' / 'nav_daemon.yaml'
            nav_cfg.parent.mkdir(parents=True)
            nav_cfg.write_text(
                '\n'.join([
                    'logging:',
                    f'  base_dir: "{root / "nav_data"}"',
                    '  split_by_date: true',
                    '',
                ]),
                encoding='utf-8',
            )

            nav_log_dir = root / 'nav_data' / '2026-03-26' / 'nav'
            nav_log_dir.mkdir(parents=True)
            (nav_log_dir / 'nav_events.csv').write_text('mono_ns,event\n1,device_bind_state_changed\n', encoding='utf-8')
            (nav_log_dir / 'nav_timing.bin').write_bytes(b'nav_timing')
            (nav_log_dir / 'nav_state.bin').write_bytes(b'nav_state')

            ctrl_root = root / 'ctrl_root'
            (ctrl_root / 'logs' / 'nav').mkdir(parents=True)
            (ctrl_root / 'logs' / 'control').mkdir(parents=True)
            (ctrl_root / 'logs' / 'telemetry').mkdir(parents=True)
            (ctrl_root / 'logs' / 'nav' / 'nav_events.csv').write_text('mono_ns,event\n2,nav_view_decision_changed\n', encoding='utf-8')
            (ctrl_root / 'logs' / 'control' / 'control_events.csv').write_text('mono_ns,event\n3,guard_reject\n', encoding='utf-8')
            control_loop = ctrl_root / 'logs' / 'control' / 'control_loop_20260326_120001.csv'
            telemetry_timeline = ctrl_root / 'logs' / 'telemetry' / 'telemetry_timeline_20260326_120001.csv'
            telemetry_events = ctrl_root / 'logs' / 'telemetry' / 'telemetry_events_20260326_120001.csv'
            control_loop.write_text('MonoNS\n1\n', encoding='utf-8')
            telemetry_timeline.write_text('telemetry_stamp_ns\n1\n', encoding='utf-8')
            telemetry_events.write_text('stamp_ns\n1\n', encoding='utf-8')

            ts = datetime.fromisoformat('2026-03-26T12:00:00+08:00').timestamp() + 10.0
            for path in (control_loop, telemetry_timeline, telemetry_events):
                os.utime(path, (ts, ts))

            child_dir = run_dir / 'child_logs' / 'uwnav_navd'
            child_dir.mkdir(parents=True)
            (child_dir / 'stdout.log').write_text('nav stdout\n', encoding='utf-8')
            (child_dir / 'stderr.log').write_text('nav stderr\n', encoding='utf-8')

            manifest = {
                'run_id': '20260326_120000_1234',
                'profile': 'bench',
                'created_wall_time': '2026-03-26T12:00:00+08:00',
                'processes': [
                    {
                        'name': 'uwnav_navd',
                        'cwd': str(root / 'nav_core'),
                        'required_paths': [str(root / 'nav_core' / 'build' / 'bin' / 'uwnav_navd'), str(nav_cfg)],
                        'log_files': {
                            'stdout': str(child_dir / 'stdout.log'),
                            'stderr': str(child_dir / 'stderr.log'),
                        },
                    },
                    {
                        'name': 'nav_viewd',
                        'cwd': str(ctrl_root),
                        'required_paths': [],
                        'log_files': {'stdout': None, 'stderr': None},
                    },
                    {
                        'name': 'pwm_control_program',
                        'cwd': str(ctrl_root),
                        'required_paths': [],
                        'log_files': {'stdout': None, 'stderr': None},
                    },
                    {
                        'name': 'gcs_server',
                        'cwd': str(ctrl_root),
                        'required_paths': [],
                        'log_files': {'stdout': None, 'stderr': None},
                    },
                ],
            }
            (run_dir / 'run_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            (run_dir / 'process_status.json').write_text(json.dumps({'run_id': manifest['run_id'], 'profile': 'bench', 'supervisor_state': 'failed'}, ensure_ascii=False, indent=2), encoding='utf-8')
            (run_dir / 'last_fault_summary.txt').write_text('event=preflight_failed\n', encoding='utf-8')
            (run_dir / 'supervisor_events.csv').write_text('mono_ns,event\n1,supervisor_started\n', encoding='utf-8')

            summary = incident_bundle.export_run_bundle(run_dir)
            self.assertTrue(summary['required_ok'])
            self.assertIn('events.uwnav_navd.nav_events', [item['key'] for item in summary['artifacts'] if item['status'] == 'copied'])
            self.assertTrue(summary['merge_robot_timeline']['ready'])

            bundle_dir = Path(summary['bundle_dir'])
            self.assertTrue((bundle_dir / 'events' / 'uwnav_navd' / 'nav_events.csv').exists())
            self.assertTrue((bundle_dir / 'events' / 'nav_viewd' / 'nav_events.csv').exists())
            self.assertTrue((bundle_dir / 'events' / 'pwm_control_program' / 'control_events.csv').exists())
            self.assertTrue((bundle_dir / 'nav' / 'nav_timing.bin').exists())
            self.assertTrue((bundle_dir / 'nav' / 'nav_state.bin').exists())
            self.assertTrue(any(path.name.startswith('control_loop_') for path in (bundle_dir / 'control').iterdir()))
            self.assertTrue(any(path.name.startswith('telemetry_timeline_') for path in (bundle_dir / 'telemetry').iterdir()))
            self.assertTrue(any(path.name.startswith('telemetry_events_') for path in (bundle_dir / 'telemetry').iterdir()))


if __name__ == '__main__':
    unittest.main()
