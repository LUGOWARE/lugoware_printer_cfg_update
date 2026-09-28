import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from repair_apt_sources import repair


class AptRepairTests(unittest.TestCase):
    def test_preserves_other_sources_and_backup_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'apt'
            root.mkdir()
            path = root / 'sources.list'
            original = (b'deb http://deb.debian.org/debian bullseye main\n'
                        b'deb-src http://deb.debian.org/debian bullseye-backports main\n'
                        b'#deb http://deb.debian.org/debian bullseye-backports main\n')
            path.write_bytes(original)
            backup = Path(tmp) / 'backup'
            self.assertEqual(repair(root, backup), 1)
            self.assertEqual((backup / 'sources.list').read_bytes(), original)
            self.assertEqual(path.read_bytes(), original.replace(b'\ndeb-src', b'\n#deb-src'))
            self.assertEqual(repair(root, backup), 0)

    def test_additional_list_and_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'apt'
            lists = root / 'sources.list.d'
            lists.mkdir(parents=True)
            path = lists / 'old.list'
            path.write_text('deb [arch=arm64] http://example.invalid bullseye-backports main\n')
            self.assertEqual(repair(root, Path(tmp) / 'backup'), 1)
            self.assertTrue(path.read_text().startswith('#deb'))

    def test_recovery_precedes_idle_check(self):
        text = (Path(__file__).resolve().parents[1] / 'install.sh').read_text(encoding='utf-8')
        self.assertLess(text.index('--recover-only'), text.index('maintenance/check_idle.py'))
