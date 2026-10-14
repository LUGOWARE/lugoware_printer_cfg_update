import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from patch_screen_identity import VERSION_METHOD, patch_version


class VersionTests(unittest.TestCase):
    def test_patch_repeatable(self):
        source = '''class BasePanel:
    def __init__(self):
        self.control["time"] = Gtk.Label(label="00:00 AM")
    def update_time(self):
        return True
    def other(self):
        return 42
'''
        result = patch_version(source)
        self.assertEqual(patch_version(result), result)
        self.assertIn('return 42', result)
        self.assertIn('attr_scale_new(0.8)', result)

    def test_existing_pango_title_is_not_shadowed(self):
        import symtable
        for old_style in ('', '        # LUGOWARE version label style\n        from gi.repository import Pango\n'):
            source = ('class BasePanel:\n'
                      '    def __init__(self):\n'
                      '        self.title = Pango.EllipsizeMode.END\n'
                      + old_style +
                      '        self.control["time"] = Gtk.Label(label="V—")\n'
                      '    def update_time(self):\n'
                      '        return True\n')
            result = patch_version(source)
            table = symtable.symtable(result, 'base_panel.py', 'exec')
            init = table.get_children()[0].get_children()[0]
            self.assertTrue(init.lookup('Pango').is_global())
            self.assertEqual(patch_version(result), result)

    def test_refresh_formats_and_missing_file(self):
        ns = {}
        exec(textwrap.dedent(VERSION_METHOD), ns)
        class Label:
            text = ''
            def set_text(self, value): self.text = value
            def get_text(self): return self.text
        label = Label()
        panel = SimpleNamespace(control={'time': label})
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            path = home / 'printer_data/config/printer_base.cfg'
            path.parent.mkdir(parents=True)
            with patch('pathlib.Path.home', return_value=home):
                for header, expected in [
                    ('# FLEX4_M_V2.128-1', 'V2.128'),
                    ('# FLEX4_W_V2.18.2', 'V2.18.2'),
                    ('# FLEX4_L_V2.19.0-beta.1', 'V2.19.0'),
                    ('# no version', 'V—'),
                ]:
                    path.write_text(header, encoding='utf-8-sig')
                    self.assertTrue(ns['update_time'](panel))
                    self.assertEqual(label.text, expected)
                path.unlink()
                self.assertTrue(ns['update_time'](panel))
                self.assertEqual(label.text, 'V—')


if __name__ == '__main__':
    unittest.main()
