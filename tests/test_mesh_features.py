import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS, ModuleType
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maintenance'))
from mesh_features import config, header
from install_mainsail_mesh import patch


class MeshTests(unittest.TestCase):
    def test_config_preserves_motion_temperature_and_pin(self):
        source = '''[extruder]
sensor_pin: PA2
[gcode_macro START_PRINT]
gcode:
    PRINT_SENSOR_BEGIN
    TEMPERATURE_WAIT SENSOR=heater_bed MINIMUM={target_BED - 5}
    HOME_CHECK
    BED_MESH_CALIBRATE
    M117 PRINTING...
    CHANGE_TOOL {ct}
    G1 X334 Y50
[gcode_macro OTHER]
gcode:
    BED_MESH_CALIBRATE
'''
        result = config(source)
        self.assertEqual(config(result), result)
        self.assertIn('SET_FILAMENT_SENSOR SENSOR=encoder_sensor ENABLE=0\n    PRINT_SENSOR_BEGIN', result)
        self.assertIn('sensor_pin: PA2', result)
        self.assertIn('MINIMUM={target_BED - 5}', result)
        self.assertIn('G1 X334 Y50', result)
        self.assertIn('SCREEN_MESH_PREPARE\n    M117 Heating...', result)
        self.assertEqual(result.count('BED_MESH_CALIBRATE'), 1)
        self.assertIn('SCREEN_MESH_AUDIT', result)

    def test_rejects_ambiguous_start(self):
        with self.assertRaises(ValueError):
            config('[gcode_macro START_PRINT]\ngcode:\n PRINT_SENSOR_BEGIN\n BED_MESH_CALIBRATE\n BED_MESH_CALIBRATE\n')

    def test_header_and_html_idempotent(self):
        source = '[mcu]\nserial: /dev/custom\n#*# <---------------------- SAVE_CONFIG ---------------------->\n'
        result = header(source, Path('/home/user/printer_data/config'))
        self.assertEqual(header(result, Path('/home/user/printer_data/config')), result)
        self.assertLess(result.index('[screen_mesh]'), result.index('#*#'))
        html = patch('<html><body></body></html>')
        self.assertEqual(patch(html), html)

    def test_off_load_and_cancel_do_not_probe(self):
        package = ModuleType('mesh_trial_tests'); package.__path__ = []
        sys.modules[package.__name__] = package
        fake = ModuleType('mesh_trial_tests.bed_mesh'); fake.ZMesh = object
        sys.modules[fake.__name__] = fake
        spec = importlib.util.spec_from_file_location('mesh_trial_tests.screen_mesh', ROOT/'maintenance/print_features/screen_mesh.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        obj = module.ScreenMesh.__new__(module.ScreenMesh)
        calls = []; restored = []
        obj.pending = False; obj.last_action = ''
        obj.cancelled = lambda: False
        obj.restore = lambda: restored.append(True)
        obj.audit = lambda phase: None
        obj.gcode = NS(run_script_from_command=calls.append, respond_raw=calls.append)
        cmd = NS(error=RuntimeError, respond_info=lambda msg: None)
        obj.prepare(cmd)
        self.assertEqual(obj.last_action, 'loaded')
        self.assertEqual(restored, [True])
        self.assertNotIn('BED_MESH_CALIBRATE', calls)
        obj.pending = False
        def missing(): raise ValueError('missing')
        obj.restore = missing
        saved = []
        obj.printer = NS(lookup_object=lambda name: NS(set_mesh=lambda mesh: None))
        obj.write_mesh = lambda: saved.append(True)
        obj.prepare(cmd)
        self.assertIn('BED_MESH_CALIBRATE', calls)
        self.assertEqual(saved, [True])
        self.assertEqual(obj.last_action, 'measured_saved')
        self.assertTrue(any(line.startswith('echo: Unable to load') for line in calls))
        # An unsuccessful measurement must still abort without saving.
        obj.pending = False
        def fail(script):
            if script == 'BED_MESH_CALIBRATE': raise RuntimeError('probe failure')
        obj.gcode.run_script_from_command = fail
        with self.assertRaises(RuntimeError): obj.prepare(cmd)
        self.assertEqual(saved, [True])
        obj.pending = True; obj.cancelled = lambda: True
        before = list(calls); obj.prepare(cmd)
        self.assertEqual(calls, before)


if __name__ == '__main__':
    unittest.main()
