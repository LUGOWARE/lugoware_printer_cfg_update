import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'maintenance'))
from install_printer_header import merge, SAVED
from install_screen_config import merge as screen_merge, SAVED as SCREEN_SAVED, blocks


class HeaderTests(unittest.TestCase):
    def test_missing_probe_offset_defaults_to_zero(self):
        for tail in ('', SAVED + '\n#*# [stepper_z]\n#*# z_offset = 9.9\n',
                     SAVED + '\n#*# [probe]\n#*# speed = 5\n'):
            old = '[mcu]\nserial: /dev/serial/M\n\n' + tail
            new = merge(old, self.template)
            self.assertIn('#*# z_offset = 0.000', new)
            self.assertEqual(new.count('#*# [probe]'), 1)
            self.assertEqual(merge(new, self.template), new)

    def test_inline_offset_migrated_and_saved_offset_wins(self):
        old = '[mcu]\nserial: /dev/serial/M\n[probe]\nz_offset: 0.543\n'
        new = merge(old, self.template)
        self.assertIn('#*# z_offset = 0.543', new)
        old += SAVED + '\n#*# [probe]\n#*# z_offset = -0.123\n'
        new = merge(old, self.template)
        self.assertIn('#*# z_offset = -0.123', new)
        self.assertNotIn('0.543', new)

    def setUp(self):
        self.template = (ROOT/'templates/printer_header.cfg').read_text(encoding='utf-8')

    def test_preserve_serial_and_saved_bytes_and_repeat(self):
        for model in 'MLW':
            old = '[mcu]\nserial: /dev/serial/' + model + '\nrestart_method: command\n\n'
            old += '[virtual_sdcard]\npath: /custom/gcodes\n\n' + SAVED + '\r\n#*# [probe]\r\n#*# z_offset = 0.321\r\n'
            new = merge(old, self.template)
            self.assertEqual(new[new.index(SAVED):], old[old.index(SAVED):])
            self.assertIn('serial: /dev/serial/' + model, new)
            self.assertIn('restart_method: command', new)
            self.assertIn('path: /custom/gcodes', new)
            self.assertEqual(merge(new, self.template), new)
            self.assertEqual(new.count('[fast_cancel]'), 1)

    def test_can_and_extra_mcus_are_preserved(self):
        old = '[mcu]\ncanbus_uuid: aabbcc\n[mcu tool]\nserial: /dev/tool\n'
        new = merge(old, self.template)
        self.assertIn('canbus_uuid: aabbcc', new)
        self.assertIn('[mcu tool]\nserial: /dev/tool', new)
        self.assertNotIn('@MCU_SERIAL@', new)

    def test_missing_connection_rejected_and_old_base_fallback(self):
        with self.assertRaises(ValueError):
            merge('', self.template)
        new = merge('[include printer_base.cfg]\n', self.template, '[mcu]\nserial: /dev/old\n')
        self.assertIn('serial: /dev/old', new)

    def test_screen_menus_match_reference_with_preferences_preserved(self):
        template = (ROOT/'templates/KlipperScreen.conf').read_text(encoding='utf-8')
        old = '[main]\nlanguage: de\n[printer Mine]\nmoonraker_host: localhost\n[menu __main obsolete]\nenable: True\n'
        old += SCREEN_SAVED + '\n#~# [main]\n#~# language = zh_CN\n#~# theme = material-darker\n'
        new = screen_merge(old, template)
        self.assertEqual(new.partition(SCREEN_SAVED)[2], old.partition(SCREEN_SAVED)[2])
        self.assertIn('language: de', new)
        self.assertIn('[printer Mine]', new)
        menus = lambda s: {m[1] for m in blocks(s) if m[1].startswith(('menu ', 'preheat '))}
        self.assertEqual(menus(new), menus(template))
        self.assertEqual(screen_merge(new, template), new)
