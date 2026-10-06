import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from patch_screen_identity import HELPER, patch_base


class IdentityTests(unittest.TestCase):
    def test_title_patch_preserves_submenu_and_is_repeatable(self):
        source = '''class Panel:
    def set_title(self, title):
        printer = "FLEX4"
        if not title:
            self.titlelbl.set_label(printer)
            return
        self.titlelbl.set_label(printer + title)
'''
        result = patch_base(source)
        compile(result, 'panel', 'exec')
        self.assertEqual(patch_base(result), result)
        self.assertIn('self.titlelbl.set_label(printer + title)', result)

    def test_current_route_and_network_changes(self):
        ns = {}
        exec(HELPER, ns)
        with patch('subprocess.check_output', side_effect=['[{"prefsrc":"192.168.0.151"}]', '[{"prefsrc":"192.168.0.93"}]']):
            self.assertEqual(ns['_lugoware_network_address'](), '192.168.0.151')
            self.assertEqual(ns['_lugoware_network_address'](), '192.168.0.93')

    def test_offline_and_fallback(self):
        ns = {}
        exec(HELPER, ns)
        with patch('subprocess.check_output', side_effect=[OSError(), '127.0.0.1 192.168.0.151']):
            self.assertEqual(ns['_lugoware_network_address'](), '192.168.0.151')
        with patch('subprocess.check_output', side_effect=OSError()):
            self.assertEqual(ns['_lugoware_network_address'](), 'IP —')
