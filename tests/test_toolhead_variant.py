import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('variant', ROOT/'maintenance/install_toolhead_variant.py')
variant = importlib.util.module_from_spec(spec)
spec.loader.exec_module(variant)


def profile():
    text = '[extruder]\nsensor_pin: PA1\n\n[filament_switch_sensor toolhead_sensor]\nswitch_pin: ^PC3\ndebounce_delay: 0.2\npause_on_runout: True\n'
    for n in range(4):
        text += ('\n[gcode_macro DOCK_TOOL_%d]\ngcode:\n    G1 X100\n'
                 '    FAST_CANCEL_WAIT P={(h_d * 1000)|int}\n' % n)
        for name in ('PARK_TOOL_', 'PARK_'):
            text += '\n[gcode_macro %s%d]\ngcode:\n    G1 X200\n' % (name, n)
    return text


class VariantTests(unittest.TestCase):
    def test_release_pid_overrides_old_saved_aux_pid(self):
        old = '[heater_generic Toolhead]\nheater_pin: PB7\npid_kp = 1\npid_ki: 2\npid_kd: 3\n'
        new = variant.pid_profile(old, 'heater_generic Toolhead', variant.TOOLHEAD_PID)
        self.assertIn('pid_kp: 37.681', new)
        self.assertIn('pid_ki: 9.191', new)
        self.assertIn('pid_kd: 38.623', new)
        self.assertIn('heater_pin: PB7', new)
        saved = '#*# [heater_generic Toolhead]\n#*# pid_kp = 1\n#*# pid_ki = 2\n#*# pid_kd = 3\n'
        saved = variant.nozzle_header_profile(saved, 'toolhead')
        self.assertIn('#*# pid_kp: 37.681', saved)
        self.assertIn('#*# pid_kd: 38.623', saved)

    def test_auxiliary_pt1000_and_standard_restoration(self):
        original = profile().replace('sensor_pin: PA1', 'sensor_type: pt1000_cal\nsensor_pin: PA1\ncontrol: pid\npid_kp: 24.053')
        aux = variant.base_profile(original, 'toolhead')
        self.assertIn('sensor_type: PT1000\n', aux)
        self.assertIn('pid_kp: 13.953', aux)
        self.assertEqual(aux, variant.base_profile(aux, 'toolhead'))
        restored = variant.base_profile(aux, 'standard')
        self.assertIn('sensor_type: pt1000_cal\n', restored)
        self.assertNotIn('lugoware_standard_sensor_type', restored)
        self.assertEqual(original, variant.base_profile(original, 'standard'))

    def test_header_and_save_config_sensor_override(self):
        original = '[extruder]\nsensor_type: pt1000_cal\n\n#*# [extruder]\n#*# sensor_type: pt1000_cal\n#*# pid_kp: 24.053\n'
        aux = variant.nozzle_header_profile(original, 'toolhead')
        self.assertEqual(aux.count('sensor_type: PT1000\n'), 2)
        self.assertIn('#*# pid_kp: 13.953', aux)
        self.assertEqual(aux, variant.nozzle_header_profile(aux, 'toolhead'))
        self.assertEqual(original, variant.nozzle_header_profile(aux, 'standard'))

    def test_round_trip_and_idempotence(self):
        original = profile()
        aux = variant.base_profile(original, 'toolhead')
        self.assertEqual(aux.count('TOOLHEAD_DOCK_HEAT TEMP='), 4)
        self.assertEqual(aux.count('    TOOLHEAD_PARK_OFF'), 8)
        self.assertEqual(aux, variant.base_profile(aux, 'toolhead'))
        standard = variant.base_profile(aux, 'standard')
        self.assertNotIn('TOOLHEAD_PARK_OFF', standard)
        self.assertIn('switch_pin: ^PC3', standard)
        self.assertIn('debounce_delay: 0.2', standard)
        moves = lambda s: [l for l in s.splitlines() if 'G1 ' in l]
        self.assertEqual(moves(original), moves(aux))
        self.assertEqual(moves(original), moves(standard))

    def test_pin_conflict_blocks(self):
        with self.assertRaises(ValueError):
            variant.base_profile(profile()+'\n[output_pin other]\npin: PB7\n', 'toolhead')

    def test_missing_macro_blocks(self):
        with self.assertRaises(ValueError):
            variant.base_profile(profile().replace('[gcode_macro PARK_2]', '[gcode_macro OTHER]'), 'toolhead')

    def test_ui_patch_roundtrip(self):
        patches = json.loads((ROOT/'maintenance/toolhead_variant/ui_patches.json').read_text(encoding='utf-8'))
        for edits in patches.values():
            for old, new in edits:
                self.assertEqual(variant.patch_ui(old, [(old, new)], 'toolhead'), new)
                self.assertEqual(variant.patch_ui(new, [(old, new)], 'toolhead'), new)
                self.assertEqual(variant.patch_ui(new, [(old, new)], 'standard'), old)

    def test_existing_double_quote_translation(self):
        patches = json.loads((ROOT/'maintenance/toolhead_variant/ui_patches.json').read_text(encoding='utf-8'))
        edits = patches['KlipperScreen/ks_includes/screen_panel.py']
        before, after = edits[0]
        installed = after.replace("_('Not attached')", '_("Not attached")')
        self.assertEqual(variant.patch_ui(installed, edits, 'toolhead'), after)
        self.assertEqual(variant.patch_ui(installed, edits, 'standard'), before)

    def test_legacy_korean_label_and_partial_upgrade(self):
        patches = json.loads((ROOT/'maintenance/toolhead_variant/ui_patches.json').read_text(encoding='utf-8'))
        edits = patches['KlipperScreen/ks_includes/screen_panel.py']
        before, after = edits[0]
        for literal in ('"미부착"', "'미부착'"):
            legacy = after.replace("_('Not attached')", literal)
            self.assertEqual(variant.patch_ui(legacy, edits, 'toolhead'), after)
            self.assertEqual(variant.patch_ui(legacy, edits, 'standard'), before)

    def test_unknown_ui_preserved(self):
        with self.assertRaises(ValueError):
            variant.patch_ui('unknown', [('a', 'b')], 'toolhead')

    def test_preflight_does_not_block_old_screen_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            config = home/'printer_data/config'
            config.mkdir(parents=True)
            (config/'printer.cfg').write_text('[mcu]\nserial: test\n')
            assets = ROOT/'maintenance/toolhead_variant'
            variant.preflight(home, 'toolhead', assets, screen_upgrade_pending=True)
            with self.assertRaisesRegex(ValueError, 'Missing UI file'):
                variant.preflight(home, 'toolhead', assets, screen_upgrade_pending=False)
            self.assertEqual((config/'printer.cfg').read_text(), '[mcu]\nserial: test\n')

    def test_standard_preflight_does_not_require_auxiliary_ui(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            config = home/'printer_data/config'
            config.mkdir(parents=True)
            (config/'printer.cfg').write_text('[mcu]\nserial: test\n')
            variant.preflight(home, 'standard', ROOT/'maintenance/toolhead_variant')
            self.assertFalse((home/'.local/share/lugoware/variant.json').exists())

    def test_atomic_write_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d);a=root/'a';a.write_bytes(b'old')
            blocked=root/'not-directory';blocked.write_bytes(b'block')
            with self.assertRaises(OSError):
                variant.commit({a:b'new', blocked/'b':b'new'}, root/'backup')
            self.assertEqual(a.read_bytes(), b'old')


if __name__ == '__main__':
    unittest.main()
