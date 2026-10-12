import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maintenance"))
import lugo_tool_temperature

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / 'tests'))
from test_tool_temperature import Tests, Command


class StartTests(Tests):
    def test_bed_live_api_during_macro_and_limits(self):
        self.objects['heater_bed'] = SimpleNamespace(heater=SimpleNamespace(min_temp=0, max_temp=130))
        self.obj.start_tool = 0
        self.obj.depth = 1
        self.obj.bed_base = 60
        self.obj.bed_ready = True
        result = []
        def request(value):
            return SimpleNamespace(get_float=lambda k: value, error=ValueError, send=result.append)
        self.obj.handle_set_bed(request(55))
        self.assertEqual(self.calls, [('heater', 55)])
        self.assertEqual(self.obj.wait_shift('heater_bed'), -5)
        self.obj.original['M140'] = lambda cmd: self.calls.append(cmd.params)
        self.obj.dispatch('M140', Command('M140', {'S': 60}))
        self.assertEqual(self.calls[-1]['S'], '55')
        self.obj.dispatch('M140', Command('M140', {'S': 0}))
        self.assertEqual(self.calls[-1]['S'], 0)
        for value in (-1, 131, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.obj.handle_set_bed(request(value))
        self.obj.printer.is_shutdown = lambda: True
        with self.assertRaises(ValueError):
            self.obj.handle_set_bed(request(55))
        self.obj.reset()
        self.assertIsNone(self.obj.bed_override)

    def test_bed_disabled_until_start_heater_command(self):
        request = SimpleNamespace(get_float=lambda k: 61, error=ValueError, send=lambda r: None)
        with self.assertRaises(ValueError):
            self.obj.handle_set_bed(request)
        self.obj.start_tool = 0
        self.obj.depth = 1
        self.obj.original['M140'] = lambda cmd: self.assertFalse(self.obj.bed_ready)
        self.obj.dispatch('M140', Command('M140', {'S': 60}))
        self.assertTrue(self.obj.get_status(0)['bed_ready'])
        self.obj.reset()
        self.assertFalse(self.obj.get_status(0)['bed_ready'])

    def setUp(self):
        super().setUp()
        self.obj.printer.is_shutdown = lambda: False
        self.obj.printer.get_start_args = lambda: {}

    def test_start_edit_before_tool_pickup_and_later_command(self):
        self.current = -1
        self.obj.start_tool = 0
        self.obj.depth = 1
        self.obj.base[0] = 220
        self.obj.set_temperature(Command('LUGO_SET_TOOL_TEMP', {'TOOL': 0, 'TEMP': 205}))
        self.assertEqual(self.calls, [('heater', 205)])
        self.obj.dispatch('M104', Command('M104', {'S': 220}))
        self.assertEqual(self.calls[-1][1]['S'], '205.0')
        self.assertEqual(self.obj.base[0], 220)

    def test_start_edit_other_tool_does_not_heat(self):
        self.obj.start_tool = 0
        self.obj.depth = 1
        self.obj.set_temperature(Command('LUGO_SET_TOOL_TEMP', {'TOOL': 1, 'TEMP': 205}))
        self.assertEqual(self.calls, [])

    def test_start_docking_preserves_boost(self):
        self.obj.start_tool = 0
        self.obj.changing = 1
        self.obj.depth = 2
        self.obj.overrides[0] = 205
        self.obj.dispatch('M104', Command('M104', {'S': 260}))
        self.assertEqual(self.calls[-1][1]['S'], 260)
        self.obj.set_temperature(Command('LUGO_SET_TOOL_TEMP', {'TOOL': 0, 'TEMP': 200}))
        self.assertEqual(len(self.calls), 1)

    def test_wait_rechecks_edited_temperature(self):
        self.obj.start_tool = 0
        self.obj.base[0] = 220
        heater = self.objects['extruder'].get_heater()
        heater.get_temp = lambda t: (200, 200)
        pauses = []
        def pause(t):
            pauses.append(t)
            self.obj.overrides[0] = 200
            if len(pauses) > 1:
                raise AssertionError('Wait did not follow lowered target')
            return t
        self.obj.printer.get_reactor = lambda: SimpleNamespace(monotonic=lambda: 0, pause=pause)
        self.objects['toolhead'] = SimpleNamespace(get_last_move_time=lambda: 0)
        self.obj.start_wait(Command('TEMPERATURE_WAIT', {'MINIMUM': 215, 'MAXIMUM': 240}))
        self.assertEqual(len(pauses), 1)

    def test_api_accepts_start_edit_and_rejects_idle(self):
        self.obj.start_tool = 0
        self.obj.depth = 1
        result = []
        request = SimpleNamespace(get_int=lambda k: 0, get_float=lambda k: 205,
                                  error=ValueError, send=result.append)
        self.obj.handle_set(request)
        self.assertEqual(self.calls, [('heater', 205)])
        self.assertEqual(result, [{'tool': 0, 'temperature': 205}])
        self.obj.active = False
        with self.assertRaises(ValueError):
            self.obj.handle_set(request)


if __name__ == '__main__':
    unittest.main()
