import sys
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maintenance/print_features'))
sys.path.insert(0, str(ROOT / 'maintenance'))
from toolchange_count import count_toolchanges, file_total
from patch_print_controls import feature_macros


class FeatureTests(unittest.TestCase):
    def test_cache_reuse_and_same_name_replacement(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            folder = Path(tmp)
            file = folder / 'part.gcode'
            cache = folder / 'cache'
            file.write_text('START_PRINT INITIAL_TOOL=0\nT1\n')
            self.assertEqual(file_total(folder, file.name, cache), 2)
            with patch('toolchange_count.count_toolchanges', side_effect=AssertionError('cache not used')):
                self.assertEqual(file_total(folder, file.name, cache), 2)
            file.write_text('START_PRINT INITIAL_TOOL=0\nT1\nT2\n')
            self.assertEqual(file_total(folder, file.name, cache), 3)

    def test_rejects_outside_gcode_root(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            with self.assertRaises(ValueError):
                file_total(tmp, '../outside.gcode', Path(tmp) / 'cache')

    def test_slicer_duplicate_selection_counts_once(self):
        lines = ['START_PRINT INITIAL_TOOL=3', 'CHANGE_TOOL NEXT_TOOL=3', 'T3',
                 'CHANGE_TOOL NEXT_TOOL=0', 'T0', '; CHANGE_TOOL NEXT_TOOL=1',
                 'CHANGE_TOOL NEXT_TOOL=2 ; comment', 'T2']
        self.assertEqual(count_toolchanges(lines), 3)

    def test_single_tool_and_empty(self):
        self.assertEqual(count_toolchanges(['START_PRINT INITIAL_TOOL=2', 'T2']), 1)
        self.assertEqual(count_toolchanges(['; T2', 'G1 X20']), 0)

    def test_macro_hooks_preserve_board_motion_and_repeat(self):
        source = '[gcode_macro TOOL_STATE]\nvariable_active_tool: -1\ngcode:\n\n'
        source += '[gcode_macro START_PRINT]\ngcode:\n    RESET_FIRSTDOCK_FLAGS\n    G1 X334 Y50\n    SET_FILAMENT_SENSOR SENSOR=toolhead_sensor ENABLE=0\n'
        source += '[gcode_macro CHANGE_TOOL]\ngcode:\n    SAVE_GCODE_STATE NAME=FAST_CANCEL_CHANGE_TOOL_STATE\n    G1 X438\n'
        for name in ('PAUSE', 'RESUME', 'END_PRINT', 'CANCEL_PRINT'):
            source += f'[gcode_macro {name}]\ngcode:\n'
            source += '  BASE_RESUME\n' if name == 'RESUME' else '    G1 Z10\n'
        result = feature_macros(source)
        self.assertEqual(feature_macros(result), result)
        motion = lambda s: [x for x in s.splitlines() if x.strip().startswith('G1 ')]
        self.assertEqual(motion(source), motion(result))
        existing_tc = '\n'.join(line for line in result.splitlines() if 'PRINT_SENSOR_' not in line) + '\n'
        upgraded = feature_macros(existing_tc)
        self.assertEqual(upgraded.count('variable_tc_count:'), 1)
        self.assertEqual(upgraded.count('VARIABLE=tc_count '), 2)
        self.assertIn('PRINT_SENSOR_BEGIN', result)
        self.assertEqual(result.count('PRINT_SENSOR_END'), 2)
        self.assertIn('BASE_RESUME\n  PRINT_SENSOR_GATE ENABLE=1', result)


if __name__ == '__main__':
    unittest.main()
