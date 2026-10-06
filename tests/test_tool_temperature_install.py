import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from install_tool_temperature import install, menu_patch


class IntegrationTests(unittest.TestCase):
    def test_menu_preserves_other_entries_and_saved_settings(self):
        source = '[menu __print temperature]\nname: Temp\nenable: True\n\n[menu __main camera]\nenable: True\n#~# [main]\n#~# language = ko\n'
        result = menu_patch(source)
        self.assertEqual(menu_patch(result), result)
        self.assertIn('[menu __main camera]\nenable: True', result)
        self.assertTrue(result.endswith('#~# language = ko\n'))
        self.assertEqual(result.count('enable: False'), 2)
        self.assertIn('panel: tool_temperature', result)

    def test_previously_hidden_temperature_is_enabled(self):
        source = '[menu __print temperature]\nenable: False\npanel: temperature\n'
        result = menu_patch(source)
        self.assertIn('enable: True\npanel: tool_temperature', result)
        self.assertEqual(menu_patch(result), result)

    def test_install_backup_and_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, screen, klipper, backup = [root / name for name in ('config', 'screen', 'klipper', 'backup')]
            cfg.mkdir()
            (screen / 'panels').mkdir(parents=True)
            (klipper / 'klippy/extras').mkdir(parents=True)
            original = '[include printer_base.cfg]\n#*# saved value\n'
            (cfg / 'printer.cfg').write_text(original)
            (cfg / 'KlipperScreen.conf').write_text('[main]\n')
            (screen / 'panels/job_status.py').write_text('item = {"panel": "temperature", "extra": extruder}\n')
            install(cfg, screen, klipper, backup)
            install(cfg, screen, klipper, backup)
            self.assertEqual((backup / 'printer.cfg').read_text(), original)
            self.assertEqual((cfg / 'printer.cfg').read_text().count('[lugo_tool_temperature]'), 1)
            self.assertIn('"tool_temperature"', (screen / 'panels/job_status.py').read_text())
