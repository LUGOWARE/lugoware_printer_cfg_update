import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maintenance"))
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from lugo_tool_temperature import ToolTemperature, metadata
from install_tool_temperature import job_patch


class Command:
    def __init__(self, name, params):
        self.name, self.params = name, params
    def get_command(self): return self.name
    def get_command_parameters(self): return self.params
    def get_float(self, key, default=None, **kwargs):
        value = float(self.params.get(key, default))
        if value < kwargs.get('minval', -float('inf')) or value > kwargs.get('maxval', float('inf')):
            raise ValueError('range')
        return value
    def get_int(self, key, **kwargs): return int(self.get_float(key, **kwargs))
    def error(self, msg): return ValueError(msg)
    def respond_info(self, msg): pass


class Tests(unittest.TestCase):
    def setUp(self):
        self.obj = ToolTemperature.__new__(ToolTemperature)
        self.obj.reset()
        self.obj.active = True
        self.obj.depth = 0
        self.current = 0
        self.obj.tool = lambda: self.current
        self.calls = []
        self.obj.gcode = SimpleNamespace(create_gcode_command=lambda n, line, p: Command(n, p))
        heater = SimpleNamespace(min_temp=0, max_temp=300)
        self.objects = {'extruder': SimpleNamespace(get_heater=lambda: heater),
                        'heaters': SimpleNamespace(set_temperature=lambda h, t, w: self.calls.append(('heater', t)))}
        self.obj.printer = SimpleNamespace(lookup_object=lambda n, default=None: self.objects.get(n, default))
        self.obj.original = {n: lambda cmd: self.calls.append((cmd.name, dict(cmd.params)))
                             for n in ('M104', 'M109', 'CHANGE_TOOL', 'END_PRINT', 'CANCEL_PRINT')}

    def test_change_preserves_override_and_other_parameters(self):
        self.obj.overrides[1] = 225
        self.obj.dispatch('CHANGE_TOOL', Command('CHANGE_TOOL', {'NEXT_TOOL': '1', 'TEMP': '230', 'H_D': '10'}))
        self.assertEqual(self.calls[0][1]['TEMP'], '225')
        self.assertEqual(self.calls[0][1]['H_D'], '10')
        self.assertEqual(self.obj.base[1], 230)

    def test_other_tool_not_overridden(self):
        self.obj.overrides[0] = 215
        self.obj.dispatch('CHANGE_TOOL', Command('CHANGE_TOOL', {'NEXT_TOOL': '2', 'TEMP': '240'}))
        self.assertEqual(self.calls[0][1]['TEMP'], '240')

    def test_layer_temperature_and_off(self):
        self.obj.overrides[0] = 215
        for target in (210, 0):
            self.obj.dispatch('M104', Command('M104', {'S': target}))
        self.assertEqual(self.calls[0][1]['S'], '215')
        self.assertEqual(self.calls[1][1]['S'], 0)

    def test_boost_is_not_clamped(self):
        self.obj.depth = 1
        self.obj.overrides[0] = 215
        self.obj.dispatch('M104', Command('M104', {'S': 255}))
        self.assertEqual(self.calls[0][1]['S'], 255)

    def test_inactive_tool_edit_no_heating(self):
        self.obj.set_temperature(Command('LUGO_SET_TOOL_TEMP', {'TOOL': 2, 'TEMP': 240}))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.obj.overrides[2], 240)

    def test_active_tool_edit_and_limits(self):
        self.obj.set_temperature(Command('LUGO_SET_TOOL_TEMP', {'TOOL': 0, 'TEMP': 220}))
        self.assertEqual(self.calls, [('heater', 220)])
        for value in (261, 0, 'nan'):
            with self.assertRaises(ValueError):
                self.obj.set_temperature(Command('LUGO_SET_TOOL_TEMP', {'TOOL': 0, 'TEMP': value}))

    def test_end_and_cancel_clear(self):
        for name in ('END_PRINT', 'CANCEL_PRINT'):
            self.obj.active = True
            self.obj.overrides[0] = 220
            self.obj.dispatch(name, Command(name, {}))
            self.assertFalse(self.obj.active)
            self.assertEqual(self.obj.overrides, [None] * 4)

    def test_docking_boost_and_final_temperature(self):
        self.obj.overrides[1] = 225
        def docking(cmd):
            target = cmd.get_float('TEMP')
            self.obj.dispatch('M104', Command('M104', {'S': target + 40}))
            self.current = 1
        self.obj.original['CHANGE_TOOL'] = docking
        self.obj.dispatch('CHANGE_TOOL', Command('CHANGE_TOOL', {'NEXT_TOOL': 1, 'TEMP': 230}))
        self.assertEqual(self.calls, [('M104', {'S': 265}), ('heater', 225)])
        self.assertEqual(self.obj.depth, 0)

    def test_failed_cancel_still_resets(self):
        def fail(cmd): raise ValueError('park failed')
        self.obj.original['CANCEL_PRINT'] = fail
        self.obj.overrides[0] = 220
        with self.assertRaises(ValueError):
            self.obj.dispatch('CANCEL_PRINT', Command('CANCEL_PRINT', {}))
        self.assertFalse(self.obj.active)
        self.assertEqual(self.obj.depth, 0)

    def test_metadata_and_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'job.gcode'
            p.write_text('; filament_type = PLA;TPU 85A;PETG;PLA\n; nozzle_temperature = 210,230,240,210\n')
            data = metadata(p)
            self.assertEqual(data['filament_type'][1], 'TPU 85A')
            self.assertEqual(data['nozzle_temperature'][2], '240')
        source = '{"panel": "temperature", "extra": extruder}\n{"panel": "temperature", "extra": dev}'
        patched = job_patch(source)
        self.assertIn('"extra": dev', patched)
        self.assertEqual(job_patch(patched), patched)
        with self.assertRaises(ValueError): job_patch('unsupported')

    def test_orca_saved_profile_names_take_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'job.gcode'
            names = ['내 PLA, 흰색 @ FLEX4', 'TPU 85A "Soft"', '아주 긴 프로필 이름 ' * 8, 'PETG']
            serialized = ';'.join('"' + n.replace('"', '\\"') + '"' for n in names)
            p.write_text('; filament_settings_id = ' + serialized + '\n; filament_type = PLA;TPU;PLA;PETG\n', encoding='utf-8')
            self.objects['virtual_sdcard'] = SimpleNamespace(file_path=lambda: str(p))
            self.obj.begin()
            self.assertEqual(self.obj.materials, names)


if __name__ == '__main__': unittest.main()
