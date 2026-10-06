import asyncio
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hide_updater', ROOT / 'maintenance/hide_klipper_updater.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SOURCE = '''class UpdateManager:
    def __init__(self):
        self.updaters = dict(klipper=1, moonraker=2, lugoware_config=3)
        self.klippy_identified_evt = None
    def _set_klipper_repo(self):
        if self.klippy_identified_evt is not None:
            self.klippy_identified_evt.set()
        self.updaters['klipper'] = 4
    async def _update_klipper_repo(self, updater, notify):
        self.updaters['klipper'] = updater
    def register_updater(self, name, config):
        self.updaters[name] = config
'''


class HideUpdaterTests(unittest.TestCase):
    def test_no_reappearance_and_other_updaters_work(self):
        result, changed = module.replacement(SOURCE)
        self.assertTrue(changed)
        ns = {}
        exec(result, ns)
        obj = ns['UpdateManager']()
        obj.klippy_identified_evt = Mock()
        obj._set_klipper_repo()
        obj.klippy_identified_evt.set.assert_called_once()
        asyncio.run(obj._update_klipper_repo(5, True))
        obj.register_updater('klipper', 6)
        obj.register_updater('moonraker', 8)
        obj.register_updater('other', 7)
        self.assertEqual(obj.updaters, dict(lugoware_config=3, other=7))
        self.assertEqual(module.replacement(result), (result, False))

    def test_existing_klipper_only_patch_migrates(self):
        old, _ = module.legacy_replacement(SOURCE)
        updated, changed = module.replacement(old)
        self.assertTrue(changed)
        self.assertEqual(updated, module.replacement(SOURCE)[0])

    def test_backup_preflight_and_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, backup = Path(tmp) / 'update_manager.py', Path(tmp) / 'backup.py'
            path.write_text(SOURCE)
            self.assertTrue(module.patch(path, backup, check=True))
            self.assertEqual(path.read_text(), SOURCE)
            self.assertFalse(backup.exists())
            self.assertTrue(module.patch(path, backup))
            self.assertFalse(module.patch(path, backup))
            self.assertEqual(backup.read_text(), SOURCE)

    def test_unknown_structure_rejected(self):
        with self.assertRaises(ValueError):
            module.replacement(SOURCE.replace('self.klippy_identified_evt.set()', 'pass'))
