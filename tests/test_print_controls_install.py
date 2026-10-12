import re
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from patch_print_controls import macros
from install_print_controls import config_patch, panel_patch, screen_patch, MHZ_PATTERN


class Tests(unittest.TestCase):
    def test_macro_repeat_preserves_probe_and_moves(self):
        source = '[probe]\nactivate_gcode:\n    G4 P200\n\n[gcode_macro START_PRINT]\ngcode:\n    G28\n'
        for tool in range(4):
            source += f'\n[gcode_macro DOCK_TOOL_{tool}]\ngcode:\n    TEMPERATURE_WAIT SENSOR=extruder MINIMUM=200\n    G1 X230\n    G4 P1000\n'
            source += f'\n[gcode_macro PARK_TOOL_{tool}]\ngcode:\n    G1 X256\n'
        result = macros(source)
        self.assertEqual(macros(result),result)
        self.assertIn('activate_gcode:\n    G4 P200',result)
        self.assertEqual(result.count('G1 X230'),4)
        self.assertEqual(result.count('G1 X256'),4)
        self.assertEqual(result.count('LUGO_CANCEL_WAIT P1000'),4)

    def test_config_before_save_and_repeat(self):
        source = '[lugo_tool_temperature]\n#*# <---------------------- SAVE_CONFIG ---------------------->\n#*# z_offset = 1\n'
        result = config_patch(source)
        self.assertEqual(config_patch(result),result)
        self.assertLess(result.index('[lugo_fast_cancel]'),result.index('#*#'))
        self.assertTrue(result.endswith('#*# z_offset = 1\n'))

    def test_screen_popup_filter_selective(self):
        source = 'class Screen:\n    def state_paused(self):\n        self.state_printing()\n        self.open_extrude()\n    def state_ready(self, wait=True):\n        pass\n    def show_popup_message(self, message, level=3, from_ws=False):\n        pass\n'
        result = screen_patch(source)
        compile(result,'screen.py','exec')
        self.assertEqual(screen_patch(result),result)
        self.assertTrue(re.fullmatch(MHZ_PATTERN,"Klipper: MCU 'CB2' configured for 50MHz but running at 46MHz!"))
        self.assertFalse(re.fullmatch(MHZ_PATTERN,"MCU 'CB2' shutdown: Timer too close"))
        self.assertFalse(re.fullmatch(MHZ_PATTERN,"MCU 'CB2' configured for 50MHz but running at 46MHz! Other error"))

    def test_cancel_route_no_success_popup(self):
        result=panel_patch('class Panel:\n    def cancel(self):\n        self._screen._ws.api.print_cancel()\n')
        compile(result,'job_status.py','exec')
        self.assertEqual(panel_patch(result),result)
        self.assertIn('printer.lugo_fast_cancel.request',result)
        self.assertIn('_lugo_cancel_pending = False',result)
        with self.assertRaises(ValueError):
            panel_patch('unsupported')


if __name__ == '__main__':
    unittest.main()
