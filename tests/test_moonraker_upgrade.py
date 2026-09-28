import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
import upgrade_moonraker as moon


class MoonrakerUpgradeTests(unittest.TestCase):
    def test_version_policy(self):
        self.assertLess(moon.version_key('v0.8.0-100-gabcd'), moon.MIN_VERSION)
        self.assertEqual(moon.version_key('v0.11.0-0-g68db047'), moon.MIN_VERSION)
        self.assertGreater(moon.version_key('v0.11.0-1-gabcd-dirty'), moon.MIN_VERSION)

    def test_newer_does_not_checkout_or_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(moon, 'output', side_effect=['v0.11.0-1-gabcd-dirty', tmp]), patch.object(moon, 'run') as run, patch.object(moon, 'wait_server'):
                moon.upgrade(Path(tmp), Path(tmp) / 'backup')
                run.assert_called_once_with('sudo', 'systemctl', 'restart', 'moonraker')

    def test_interrupted_install_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / 'lugoware-moonraker-pending'
            marker.touch()
            with patch.object(moon, 'output', side_effect=['v0.11.0-0-g68db047', tmp]), patch.object(moon, 'run') as run, patch.object(moon, 'wait_server'):
                moon.upgrade(root, root / 'backup')
                self.assertFalse(marker.exists())
                self.assertTrue(any(c.args[0] == 'bash' for c in run.call_args_list))
                self.assertFalse(any('checkout' in c.args for c in run.call_args_list))

    def test_failure_keeps_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / 'lugoware-moonraker-pending'
            marker.touch()
            with patch.object(moon, 'output', side_effect=['v0.11.0-0-g68db047', tmp]), patch.object(moon, 'run', side_effect=[None, RuntimeError('install failed')]):
                with self.assertRaises(RuntimeError):
                    moon.upgrade(root, root / 'backup')
                self.assertTrue(marker.exists())

    def test_unknown_edits_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(moon, 'output', side_effect=['v0.8.0-0-gabcd', tmp, 'moonraker/server.py']), patch.object(moon, 'run') as run:
                with self.assertRaises(RuntimeError):
                    moon.upgrade(Path(tmp), Path(tmp) / 'backup')
                run.assert_not_called()

    def test_install_order_and_no_legacy_patch_preflight(self):
        text = (Path(__file__).resolve().parents[1] / 'install.sh').read_text(encoding='utf-8')
        stages = ['python3 -u "$COMMON_DIR/repo/maintenance/' + name for name in
                  ('upgrade_klipper.py', 'upgrade_klipperscreen.py', 'upgrade_moonraker.py', 'update_components.py')]
        positions = [text.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))
        self.assertGreater(text.index('maintenance/hide_klipper_updater.py'), positions[2])
        self.assertGreater(text.index('bash "$COMMON_DIR/repo/maintenance/apply.sh"'), positions[-1])
        self.assertEqual(text.count('python3 -u "$COMMON_DIR/repo/maintenance/update_components.py"'), 1)


if __name__ == '__main__':
    unittest.main()
