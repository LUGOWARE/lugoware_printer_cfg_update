import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
# Only imports are stubbed on Windows. No system operations run in these tests.
if sys.platform == 'win32':
    sys.modules.setdefault('pwd', types.SimpleNamespace())
    sys.modules.setdefault('fcntl', types.SimpleNamespace())
import channel_worker as worker
from install_update_channels import configuration, service_units
from lugoware_updates import UpdateStatus
from install_tool_temperature import install as install_temperature
from install_print_controls import install as install_controls


class ChannelTests(unittest.TestCase):
    def test_config_entries_are_idempotent_and_preserve_other_sections(self):
        old = '[server]\nhost: 0.0.0.0\n[update_manager lugoware_config]\ntype: git_repo\n[other]\nvalue: yes\n'
        result = configuration(old, 'FLEX4_W')
        self.assertEqual(result, configuration(result, 'FLEX4_W'))
        self.assertIn('[other]\nvalue: yes', result)
        self.assertEqual(result.count('[update_manager lugoware_config]'), 1)
        self.assertEqual(result.count('[update_manager lugoware_system]'), 1)
        self.assertIn('primary_branch: FLEX4_W', result)
        self.assertIn('primary_branch: main', result)
        self.assertNotIn('managed_services: klipper', result)

    def test_trigger_does_not_restart_running_worker(self):
        units = service_units('biqu', Path('/home/biqu'), 'system')
        self.assertIn('start --no-block', units['lugoware_system.service'])
        self.assertNotIn('restart ', units['lugoware_system.service'])
        self.assertIn('User=biqu', units['lugoware-system-worker.service'])
        self.assertIn('Restart=no', units['lugoware-system-worker.service'])

    def fixture(self, root):
        home, repo, backup = [root / n for n in ('home', 'repo', 'backup')]
        target = home / 'printer_data/config'
        for p in (target, repo, backup): p.mkdir(parents=True)
        for name, value in {'printer_base.cfg': 'old', 'KlipperScreen.conf': '[main]\nlanguage: ko\n',
                            'printer.cfg': '#*# z_offset = 0.543', 'printer_custom.cfg': 'custom',
                            'crowsnest.conf': 'camera'}.items():
            (target / name).write_text(value)
        (repo / 'printer_base.cfg').write_text('[printer]\nkinematics: cartesian\n')
        (repo / 'KlipperScreen.conf').write_text('[main]\nlanguage: en\n[menu __main test]\nname: Test\n')
        return home, repo, backup, target

    def test_config_only_changes_two_files_and_keeps_language(self):
        with tempfile.TemporaryDirectory() as d:
            home, repo, backup, target = self.fixture(Path(d))
            before = {p.name: p.read_bytes() for p in target.iterdir()}
            with patch.object(worker, 'validate_config'), patch.object(worker, 'check_idle'), patch.object(worker.subprocess, 'run'):
                worker.apply_config(repo, home, backup)
            for name in ('printer.cfg', 'printer_custom.cfg', 'crowsnest.conf'):
                self.assertEqual((target / name).read_bytes(), before[name])
            self.assertIn('language: ko', (target / 'KlipperScreen.conf').read_text())
            self.assertEqual((backup / 'printer_base.cfg').read_bytes(), b'old')

    def test_validation_failure_does_not_touch_files(self):
        with tempfile.TemporaryDirectory() as d:
            home, repo, backup, target = self.fixture(Path(d))
            before = {p.name: p.read_bytes() for p in target.iterdir()}
            with patch.object(worker, 'validate_config', side_effect=ValueError('system first')):
                with self.assertRaises(ValueError): worker.apply_config(repo, home, backup)
            self.assertEqual(before, {p.name: p.read_bytes() for p in target.iterdir()})

    def test_printing_blocks_writes_and_restarts(self):
        with tempfile.TemporaryDirectory() as d:
            home, repo, backup, target = self.fixture(Path(d))
            with patch.object(worker, 'validate_config'), patch.object(worker, 'check_idle', side_effect=SystemExit('printing')), patch.object(worker.subprocess, 'run') as run:
                with self.assertRaises(SystemExit): worker.apply_config(repo, home, backup)
                run.assert_not_called()
            self.assertEqual((target / 'printer_base.cfg').read_text(), 'old')

    def test_write_failure_restores_both_files(self):
        with tempfile.TemporaryDirectory() as d:
            home, repo, backup, target = self.fixture(Path(d))
            original = worker.atomic
            count = 0
            def fail_second(path, data):
                nonlocal count
                count += 1
                if count == 2: raise OSError('disk failure')
                original(path, data)
            with patch.object(worker, 'validate_config'), patch.object(worker, 'check_idle'), patch.object(worker, 'atomic', side_effect=fail_second):
                with self.assertRaises(OSError): worker.apply_config(repo, home, backup)
            self.assertEqual((target / 'printer_base.cfg').read_text(), 'old')
            self.assertEqual((target / 'KlipperScreen.conf').read_text(), '[main]\nlanguage: ko\n')

    def test_missing_backend_command_blocks_config(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            extras = home / 'klipper/klippy/extras'
            extras.mkdir(parents=True)
            for name in ('fast_cancel.py', 'lugo_tool_temperature.py'):
                (extras / name).write_text('')
            with patch.object(worker, 'macros'):
                with self.assertRaisesRegex(ValueError, 'system first'):
                    worker.validate_config('[gcode_macro TEST]\ngcode:\n  FAST_CANCEL_NEW_FEATURE\n', '', home)

    def test_waits_for_moonraker_lock_release(self):
        with patch.object(worker, 'request', side_effect=[{'busy': True}, {'busy': False}]), patch.object(worker.time, 'sleep') as sleep:
            worker.wait_manager()
            sleep.assert_called_once_with(2)

    def test_config_waits_for_system_and_rejects_failed_system(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            path = folder / 'system-status.json'
            path.write_text('{"state":"running"}')
            with patch.object(worker.time, 'sleep', side_effect=lambda _: path.write_text('{"state":"complete"}')):
                worker.wait_system(folder)
            path.write_text('{"state":"failed"}')
            with self.assertRaisesRegex(RuntimeError, 'lugoware_system'):
                worker.wait_system(folder)

    def test_system_temperature_installer_preserves_screen_config(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cfg, screen, klipper, backup = [root / n for n in ('config', 'screen', 'klipper', 'backup')]
            cfg.mkdir(); (screen / 'panels').mkdir(parents=True); (klipper / 'klippy/extras').mkdir(parents=True)
            (cfg / 'KlipperScreen.conf').write_text('[main]\nlanguage: ko\n')
            (cfg / 'printer.cfg').write_text('[lugo_tool_temperature]\n')
            (screen / 'panels/job_status.py').write_text('item = {"panel": "temperature", "extra": extruder}\n')
            with patch.dict('os.environ', {'LUGOWARE_SYSTEM_ONLY': '1'}):
                install_temperature(cfg, screen, klipper, backup)
            self.assertEqual((cfg / 'KlipperScreen.conf').read_text(), '[main]\nlanguage: ko\n')
            self.assertTrue((klipper / 'klippy/extras/lugo_tool_temperature.py').exists())

    def test_system_controls_do_not_rewrite_or_require_new_config(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d)
            (cfg / 'printer.cfg').write_text('[fast_cancel]\n')
            (cfg / 'printer_base.cfg').write_text('old model configuration')
            with patch.dict('os.environ', {'LUGOWARE_SYSTEM_ONLY': '1'}), patch('install_print_controls.macros', side_effect=AssertionError('must not rewrite')):
                install_controls(cfg, cfg, cfg, cfg / 'backup', config_only=True)
            self.assertEqual((cfg / 'printer_base.cfg').read_text(), 'old model configuration')

    def test_failure_announcement_survives_restart_without_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            status = UpdateStatus.__new__(UpdateStatus)
            status.folder = Path(d)
            status.announcements = Mock()
            (status.folder / 'system-status.json').write_text(json.dumps(dict(run_id='1', state='failed', detail='bad', log='log')))
            status.poll(0)
            status.poll(1)
            status.announcements.add_internal_announcement.assert_called_once()
            self.assertEqual(status.announcements.add_internal_announcement.call_args.args[3], 'high')


if __name__ == '__main__':
    unittest.main()
