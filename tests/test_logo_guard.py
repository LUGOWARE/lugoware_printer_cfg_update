import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

SPEC = importlib.util.spec_from_file_location(
    'logo_guard', Path(__file__).resolve().parents[1] / 'maintenance/logo_guard.py')
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class LogoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = {'watermark.png': b'\x89PNG\r\n\x1a\n' + b'custom' * 20,
                         'boot.bmp': b'BM' + b'custom' * 20}
        for name, dest in guard.ASSETS.items():
            guard.atomic_write(guard.path(self.root, dest), self.original[name])
        self.run = Mock()

    def test_reinstall_never_replaces_first_backup(self):
        guard.backup(self.root)
        for name, dest in guard.ASSETS.items():
            guard.atomic_write(guard.path(self.root, dest), b'replaced')
        guard.backup(self.root)
        for name in guard.ASSETS:
            self.assertEqual((guard.path(self.root, guard.STORE) / name).read_bytes(),
                             self.original[name])

    def test_package_overwrite_restores_both_and_rebuilds_once(self):
        guard.backup(self.root)
        for dest in guard.ASSETS.values():
            guard.atomic_write(guard.path(self.root, dest), b'package default')
        guard.restore(self.root, run=self.run)
        self.run.assert_called_once_with(['update-initramfs', '-u', '-k', 'all'], check=True)
        for name, dest in guard.ASSETS.items():
            self.assertEqual(guard.path(self.root, dest).read_bytes(), self.original[name])
        guard.restore(self.root, run=self.run)
        self.assertEqual(self.run.call_count, 1)

    def test_boot_only_restore_does_not_rebuild_initramfs(self):
        guard.backup(self.root)
        guard.path(self.root, '/boot/boot.bmp').unlink()
        guard.restore(self.root, run=self.run)
        self.run.assert_not_called()
        self.assertEqual(guard.path(self.root, '/boot/boot.bmp').read_bytes(), self.original['boot.bmp'])

    def test_failed_rebuild_is_retried_even_after_file_restored(self):
        guard.backup(self.root)
        self.run.side_effect = subprocess.CalledProcessError(1, 'update-initramfs')
        with self.assertRaises(subprocess.CalledProcessError):
            guard.restore(self.root, force=True, run=self.run)
        self.run.side_effect = None
        guard.restore(self.root, run=self.run)
        self.assertEqual(self.run.call_count, 2)
        self.assertFalse((guard.path(self.root, guard.STORE) / '.initramfs-pending').exists())

    def test_missing_asset_blocks_first_install(self):
        guard.path(self.root, '/boot/boot.bmp').unlink()
        with self.assertRaises(FileNotFoundError):
            guard.install(self.root, run=self.run)
        self.run.assert_not_called()

    def test_install_registers_all_three_mechanisms(self):
        guard.install(self.root, run=self.run)
        self.run.assert_any_call(['systemctl', 'is-enabled', '--quiet', 'lugoware-logo.service'], check=True)
        for filename in ('/etc/apt/apt.conf.d/99lugoware-logo',
                         '/etc/initramfs-tools/hooks/zz-lugoware-logo',
                         '/etc/systemd/system/lugoware-logo.service'):
            self.assertTrue(guard.path(self.root, filename).is_file())
        self.assertFalse(any('apt-mark' in str(call) for call in self.run.call_args_list))

    def test_registration_failure_propagates(self):
        self.run.side_effect = subprocess.CalledProcessError(1, 'systemctl')
        with self.assertRaises(subprocess.CalledProcessError):
            guard.install(self.root, run=self.run)


if __name__ == '__main__':
    unittest.main()
