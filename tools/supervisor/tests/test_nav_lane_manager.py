from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.supervisor import nav_lane_manager


class NavLaneManagerTests(unittest.TestCase):
    def test_read_and_write_dvl_enable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            nav_cfg = Path(tmpdir) / 'nav_daemon.yaml'
            nav_cfg.write_text(
                '\n'.join(
                    [
                        'imu:',
                        '  enable: true',
                        'dvl:',
                        '  enable: false',
                        '  driver:',
                        '    port: "/dev/ttyACM0"',
                        '',
                    ]
                ),
                encoding='utf-8',
            )

            self.assertFalse(nav_lane_manager.read_dvl_enable(nav_cfg))
            changed = nav_lane_manager.write_dvl_enable(nav_cfg, True)
            self.assertTrue(changed)
            self.assertTrue(nav_lane_manager.read_dvl_enable(nav_cfg))
            changed = nav_lane_manager.write_dvl_enable(nav_cfg, True)
            self.assertFalse(changed)

    def test_build_navd_env_marks_operator_dvl_policy_restart(self) -> None:
        env = nav_lane_manager.build_navd_env(dvl_enabled=True)
        self.assertEqual('dvl_policy_applied', env[nav_lane_manager.OPERATOR_POLICY_EVENT_ENV])
        self.assertEqual('nav_lane_manager', env[nav_lane_manager.OPERATOR_POLICY_SOURCE_ENV])
        self.assertEqual('1', env[nav_lane_manager.OPERATOR_POLICY_DVL_ENABLED_ENV])

    def test_apply_dvl_policy_rolls_back_config_when_restart_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            nav_cfg = tmp_root / 'nav_daemon.yaml'
            nav_cfg.write_text(
                '\n'.join(
                    [
                        'imu:',
                        '  enable: true',
                        'dvl:',
                        '  enable: false',
                        '  driver:',
                        '    port: "/dev/ttyACM0"',
                        '',
                    ]
                ),
                encoding='utf-8',
            )
            state_file = tmp_root / 'state.json'

            with mock.patch.object(nav_lane_manager, 'DEFAULT_NAV_CFG', nav_cfg), mock.patch.object(
                nav_lane_manager, 'ensure_required_paths'
            ), mock.patch.object(
                nav_lane_manager, 'stop_tracked_nav_processes'
            ), mock.patch.object(
                nav_lane_manager, 'detect_untracked_nav_processes', return_value=['123 nav_viewd']
            ):
                with self.assertRaisesRegex(RuntimeError, 'untracked nav processes'):
                    nav_lane_manager.apply_dvl_policy(True, state_file)

            self.assertFalse(nav_lane_manager.read_dvl_enable(nav_cfg))


if __name__ == '__main__':
    unittest.main()
