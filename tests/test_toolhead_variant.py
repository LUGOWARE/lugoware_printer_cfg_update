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

    def test_unknown_ui_preserved(self):
        with self.assertRaises(ValueError):
            variant.patch_ui('unknown', [('a', 'b')], 'toolhead')

    def test_atomic_write_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d);a=root/'a';a.write_bytes(b'old')
            blocked=root/'not-directory';blocked.write_bytes(b'block')
            with self.assertRaises(OSError):
                variant.commit({a:b'new', blocked/'b':b'new'}, root/'backup')
            self.assertEqual(a.read_bytes(), b'old')


if __name__ == '__main__':
    unittest.main()
