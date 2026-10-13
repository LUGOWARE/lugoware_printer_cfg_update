import re
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from patch_print_controls import macros
from install_print_controls import config_patch, panel_patch, screen_patch, MHZ_PATTERN


class Tests(unittest.TestCase):
    def test_final_macros_are_preserved_and_legacy_is_rejected(self):
        source = ''.join('[gcode_macro '+name+']\ngcode:\n    G1 X334\n' for name in
                         ['CANCEL_PRINT','_FAST_CANCEL_MOTION','_FAST_CANCEL_RETURN','_FAST_CANCEL_FINALIZE','PAUSE','RESUME'])
        for tool in range(4):
            source += f'    FAST_CANCEL_PRIME STATE=begin TOOL={tool}\n    FAST_CANCEL_PRIME STATE=end TOOL={tool} EXIT_X=366\n    FAST_CANCEL_PHASE PHASE=docked TOOL={tool}\n'
        self.assertEqual(macros(source),source)
        self.assertEqual(macros(macros(source)),source)
        with self.assertRaises(ValueError): macros('[gcode_macro START_PRINT]\ngcode:\n    G28\n')
        with self.assertRaises(ValueError): macros(source+'    LUGO_CANCEL_PHASE PHASE=normal\n')

    def test_config_before_save_and_repeat(self):
        source = '[lugo_tool_temperature]\n#*# <---------------------- SAVE_CONFIG ---------------------->\n#*# z_offset = 1\n'
        result = config_patch(source)
        self.assertEqual(config_patch(result),result)
        self.assertLess(result.index('[fast_cancel]'),result.index('#*#'))
        self.assertTrue(result.endswith('#*# z_offset = 1\n'))

    def test_screen_popup_filter_selective(self):
        source = 'class Screen:\n    def state_paused(self):\n        self.state_printing()\n        self.open_extrude()\n    def state_ready(self, wait=True):\n        pass\n    def show_popup_message(self, message, level=3, from_ws=False):\n        pass\n'
        result = screen_patch(source)
        compile(result,'screen.py','exec')
        self.assertEqual(screen_patch(result),result)
        self.assertTrue(re.fullmatch(MHZ_PATTERN,"Klipper: MCU 'CB2' configured for 50MHz but running at 46MHz!"))
        self.assertTrue(re.fullmatch(MHZ_PATTERN,"Klipper: MCU 'CB2' configured for 50Mhz but running at 46Mhz!"))
        self.assertTrue(re.fullmatch(MHZ_PATTERN,"Klipper: MCU 'CB2' configured for 50mhz but running at 46mhz!"))
        legacy = result.replace(repr(MHZ_PATTERN), repr(MHZ_PATTERN[4:]))
        self.assertEqual(screen_patch(legacy), result)
        self.assertFalse(re.fullmatch(MHZ_PATTERN,"MCU 'CB2' shutdown: Timer too close"))
        self.assertFalse(re.fullmatch(MHZ_PATTERN,"MCU 'CB2' configured for 50MHz but running at 46MHz! Other error"))

    def test_cancel_route_no_success_popup(self):
        result=panel_patch('class Panel:\n    def cancel(self):\n        self._screen._ws.api.print_cancel()\n')
        compile(result,'job_status.py','exec')
        self.assertEqual(panel_patch(result),result)
        self.assertIn('printer.fast_cancel.request',result)
        self.assertIn('_lugo_cancel_pending = False',result)
        with self.assertRaises(ValueError):
            panel_patch('unsupported')


if __name__ == '__main__':
    unittest.main()
