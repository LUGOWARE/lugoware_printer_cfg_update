from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from install_screen_session import patch


class ScreenSessionTests(unittest.TestCase):
    def test_xinit_is_wrapped_without_changing_client_or_wayland(self):
        source = 'start_x11() {\n    exec /usr/bin/xinit $KS_XCLIENT\n}\nexec /usr/bin/cage -ds $KS_XCLIENT\n'
        result = patch(source)
        self.assertIn('exec /usr/bin/dbus-run-session -- /usr/bin/xinit $KS_XCLIENT', result)
        self.assertIn('exec /usr/bin/cage -ds $KS_XCLIENT', result)
        self.assertEqual(patch(result), result)

    def test_unknown_launcher_fails_before_writing(self):
        with self.assertRaises(ValueError):
            patch('exec unknown-launcher')
