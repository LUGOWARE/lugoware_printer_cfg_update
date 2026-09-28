import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from allow_sonar_service import allow_sonar


class AllowSonarTests(unittest.TestCase):
    def test_preserves_entries_backups_and_is_idempotent(self):
        for original in (b'klipper\nmoonraker', b'# services\r\nklipper\r\n'):
            with tempfile.TemporaryDirectory() as tmp:
                path, backup = Path(tmp) / 'moonraker.asvc', Path(tmp) / 'backup'
                path.write_bytes(original)
                self.assertTrue(allow_sonar(path, backup))
                self.assertEqual(backup.read_bytes(), original)
                self.assertTrue(path.read_bytes().startswith(original))
                first = path.read_bytes()
                self.assertFalse(allow_sonar(path, backup))
                self.assertEqual(path.read_bytes(), first)
                self.assertEqual(backup.read_bytes(), original)

    def test_existing_entry_and_commented_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, backup = Path(tmp) / 'moonraker.asvc', Path(tmp) / 'backup'
            path.write_text('klipper\n  sonar  \n')
            self.assertFalse(allow_sonar(path, backup))
            self.assertFalse(backup.exists())
            path.write_text('# sonar\n')
            self.assertTrue(allow_sonar(path, backup))

    def test_missing_list_is_not_replaced_with_sonar_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'moonraker.asvc'
            with self.assertRaises(FileNotFoundError):
                allow_sonar(path, Path(tmp) / 'backup')
            self.assertFalse(path.exists())

    def test_installer_reloads_before_updates(self):
        text = (Path(__file__).resolve().parents[1] / 'install.sh').read_text(encoding='utf-8')
        allow = text.index('maintenance/allow_sonar_service.py')
        restart = text.index('sudo systemctl restart moonraker', allow)
        updates = text.index('maintenance/update_components.py')
        self.assertLess(allow, restart)
        self.assertLess(restart, updates)
