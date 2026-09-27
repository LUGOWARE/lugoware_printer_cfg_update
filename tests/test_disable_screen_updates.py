import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('disable_screen_updates', Path(__file__).resolve().parents[1] / 'maintenance/disable_screen_updates.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DisableScreenUpdatesTests(unittest.TestCase):
    def test_include_tree_three_components_and_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / 'moonraker.conf'
            included = root / 'updates.conf'
            main.write_text('[include updates.conf]\n[update_manager klipper]\ntype: git_repo\n[update_manager lugoware_config]\ntype: git_repo\n')
            included.write_text('[include moonraker.conf]\n[update_manager KlipperScreen]\ntype: git_repo\n[update_manager mainsail-config]\ntype: git_repo\n[update_manager mainsail]\ntype: web\n')
            originals = {p: p.read_bytes() for p in (main, included)}
            names = ('klipper', 'KlipperScreen', 'mainsail-config')
            self.assertTrue(module.apply_tree(main, root / 'backup', names))
            self.assertIn('#[update_manager klipper]', main.read_text())
            self.assertIn('\n[update_manager lugoware_config]', main.read_text())
            self.assertIn('#[update_manager mainsail-config]', included.read_text())
            self.assertIn('\n[update_manager mainsail]', included.read_text())
            self.assertEqual({p.read_bytes() for p in (root / 'backup').iterdir()}, set(originals.values()))
            self.assertFalse(module.apply_tree(main, root / 'backup', names))
    def test_only_target_section_and_repeat(self):
        before = '[server]\nport: 7125\n\n[update_manager KlipperScreen]\ntype: git_repo\n# keep comment\npath: ~/KlipperScreen\n\n[update_manager klipper]\ntype: git_repo\n'
        after = module.comment_section(before)
        self.assertIn('#[update_manager KlipperScreen]\n#type: git_repo\n# keep comment\n#path:', after)
        self.assertTrue(after.startswith('[server]\nport: 7125'))
        self.assertTrue(after.endswith('[update_manager klipper]\ntype: git_repo\n'))
        self.assertEqual(module.comment_section(after), after)

    def test_backup_preserved_and_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'moonraker.conf'
            backup = Path(tmp) / 'backup' / 'moonraker.conf'
            original = b'[update_manager KlipperScreen]\r\ntype: git_repo\r\n'
            path.write_bytes(original)
            self.assertTrue(module.apply(path, backup))
            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual(path.read_bytes(), b'#[update_manager KlipperScreen]\r\n#type: git_repo\r\n')
            self.assertFalse(module.apply(path, backup))
            self.assertEqual(backup.read_bytes(), original)

    def test_absent_section_unchanged(self):
        for text in ('[server]\nport: 7125\n', '#[update_manager KlipperScreen]\n#type: git_repo\n'):
            self.assertEqual(module.comment_section(text), text)
