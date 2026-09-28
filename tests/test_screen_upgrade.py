import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
import upgrade_klipperscreen as screen


class ScreenUpgradeTests(unittest.TestCase):
    def test_version_boundaries(self):
        for version in ('v0.4.2-21-g18ec115-dirty', 'v0.4.7-190-g1234'):
            self.assertLess(screen.version_key(version), screen.MIN_VERSION)
        for version in ('v0.4.7-191-g3f08a9f-dirty', 'v0.4.7-192-g1234', 'v0.4.8-0-g1234', 'v0.5.0-0-g1234'):
            self.assertGreaterEqual(screen.version_key(version), screen.MIN_VERSION)
        with self.assertRaises(ValueError):
            screen.version_key('unknown')

    def test_current_or_newer_never_mutates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for version in ('v0.4.7-191-g3f08a9f', 'v0.5.0-0-g1234'):
                with patch.object(screen, 'output', side_effect=[version, tmp]), patch.object(screen, 'run') as run:
                    screen.upgrade(root, root / 'backup', root / 'env')
                    run.assert_not_called()
                    self.assertFalse((root / 'backup').exists())

    def test_preflight_does_not_stop_or_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'bin').mkdir()
            (root / 'bin/python').touch()
            with patch.object(screen, 'output', side_effect=['v0.4.2-21-g1234', tmp]), patch.object(screen, 'run') as run:
                screen.upgrade(root, root / 'backup', root, check=True)
                run.assert_not_called()

    def test_interrupted_dependencies_resume_without_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'bin').mkdir()
            (root / 'bin/python').touch()
            pending = root / 'lugoware-screen-pending'
            pending.write_text(screen.BASELINE)
            with patch.object(screen, 'output', side_effect=['v0.4.7-191-g3f08a9f', tmp, 'v0.4.7-191-g3f08a9f']), patch.object(screen, 'run') as run:
                screen.upgrade(root, root / 'backup', root)
                self.assertFalse(pending.exists())
                self.assertFalse(any('checkout' in call.args for call in run.call_args_list))
                self.assertTrue(any('pip' in call.args for call in run.call_args_list))

    def test_failed_dependencies_keep_recovery_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'bin').mkdir()
            (root / 'bin/python').touch()
            pending = root / 'lugoware-screen-pending'
            pending.write_text(screen.BASELINE)
            with patch.object(screen, 'output', side_effect=['v0.4.7-191-g3f08a9f', tmp]), patch.object(screen, 'run', side_effect=[None, RuntimeError('pip failed')]):
                with self.assertRaises(RuntimeError):
                    screen.upgrade(root, root / 'backup', root)
                self.assertTrue(pending.exists())

    def test_installer_order(self):
        source = (Path(__file__).resolve().parents[1] / 'install.sh').read_text(encoding='utf-8')
        upgrade = source.index('python3 -u "$COMMON_DIR/repo/maintenance/upgrade_klipperscreen.py"')
        panels = source.index('python3 "$COMMON_DIR/repo/maintenance/install_panels.py"', upgrade)
        maintenance = source.index('bash "$COMMON_DIR/repo/maintenance/apply.sh"', panels)
        hide = source.index('updates_result=', maintenance)
        self.assertLess(upgrade, panels)
        self.assertLess(panels, maintenance)
        self.assertLess(maintenance, hide)

    def test_old_version_backup_and_pinned_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'screen'
            folder.mkdir()
            (folder / 'custom.txt').write_text('keep in backup')
            env = root / 'env'
            (env / 'bin').mkdir(parents=True)
            (env / 'bin/python').touch()
            backup = root / 'backup'
            answers = ['v0.4.2-21-g1234', tmp, 'old-commit', 'requirements',
                       'v0.4.7-191-g3f08a9f', 'v0.4.7-191-g3f08a9f']
            with patch.object(screen, 'output', side_effect=answers), patch.object(screen.subprocess, 'check_output', return_value=b'patch'), patch.object(screen, 'run') as run:
                screen.upgrade(folder, backup, env)
                self.assertEqual((backup / 'source/custom.txt').read_text(), 'keep in backup')
                calls = [call.args for call in run.call_args_list]
                checkout = next(i for i, call in enumerate(calls) if 'checkout' in call)
                stash = next(i for i, call in enumerate(calls) if 'stash' in call)
                pip = next(i for i, call in enumerate(calls) if 'pip' in call)
                self.assertLess(stash, checkout)
                self.assertLess(checkout, pip)
                self.assertEqual(calls[checkout][-1], screen.BASELINE)
                self.assertFalse((root / 'lugoware-screen-pending').exists())


if __name__ == '__main__':
    unittest.main()
