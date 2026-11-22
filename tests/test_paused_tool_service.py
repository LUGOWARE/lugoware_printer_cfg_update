from types import SimpleNamespace as Obj
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance/paused_tool_service'))
from paused_tool_service import PausedToolService


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.position = [0., 168., 25., 0.]
        self.sensor_state = 'disconnected'
        self.homed = 'xyz'
        self.trace = []
        self.time = 0.
        self.errors = ValueError
        self.commands = {}
        self.sd = Obj(current_file=object(), is_active=lambda: False)
        self.pause = Obj(is_paused=True, sd_paused=True)
        self.fast = Obj(phase='empty', requested=False, cleaning=False, critical=False)
        self.saved = {'PAUSE_STATE': {'last_position': [7., 8., 20., 13.]}}
        self.nozzle, self.aux = self.heater(), self.heater()
        self.route = {'retry_x': 367.5, 'retry_y': 178.5, 'retry_exit': (366., 361., 334.5)}
        self.switch_enabled = True
        self.reactor = Obj(monotonic=lambda: self.time, pause=self.advance)
        objects = {
            'gcode': Obj(register_command=self.commands.__setitem__, run_script_from_command=self.run_script,
                         gcode_handlers={'_TOOL_RETRY_DOCK_XY_T2': None, '_TOOL_RETRY_PARK_XY_T2': None}),
            'fast_cancel': self.fast, 'pause_resume': self.pause, 'virtual_sdcard': self.sd,
            'print_stats': Obj(get_status=lambda _: {'state': 'paused'}),
            'extruder': Obj(get_heater=lambda: self.nozzle), 'heater_generic Toolhead': self.aux,
            'toolhead': Obj(get_status=lambda _: {'homed_axes': self.homed, 'position': self.position,
                                                 'axis_minimum': [0, 0, 0], 'axis_maximum': [381, 257, 375]}),
            'gcode_move': Obj(saved_states=self.saved, position_with_transform=lambda: self.position,
                              get_status=lambda _: {
                'gcode_position': self.position, 'position': self.position}),
            'gcode_macro _TOOL_RETRY_DOCK_XY_T2': Obj(get_status=lambda _: self.route),
            'gcode_macro _TOOL_RETRY_PARK_XY_T2': Obj(),
            'filament_switch_sensor toolhead_sensor': Obj(get_status=lambda _: {
                'filament_detected': self.sensor_state == 'connected', 'enabled': self.switch_enabled}),
            'toolhead_auxiliary': Obj(get_status=lambda _: {'state': self.sensor_state, 'temperature': 25.},
                heater_adapter=Obj(failed=False, valid_samples=9, minimum=0, maximum=300),
                sync_manual_preheat=True),
        }
        self.objects = objects
        printer = Obj(get_reactor=lambda: self.reactor, lookup_object=objects.get,
                      register_event_handler=lambda *args: None, is_shutdown=lambda: False)
        self.service = PausedToolService(Obj(get_printer=lambda: printer))
        self.gcmd = Obj(get_int=lambda *a, **kw: 1, get_float=lambda *a, **kw: 220., error=ValueError)
        self.dock_detects = True

    def advance(self, t):
        self.time = t

    def heater(self):
        h = Obj(target_temp=0., last_pwm_value=0., min_temp=0., max_temp=300., get_pwm_delay=lambda: .1)
        h.set_temp = lambda v: setattr(h, 'target_temp', v)
        return h

    def run_script(self, script):
        for line in script.splitlines():
            self.trace.append(line)
            if line.startswith('_TOOL_RETRY_DOCK_XY_T2'):
                self.position[:2] = [self.route['retry_x'], self.route['retry_y']]
                if self.dock_detects:
                    self.sensor_state = 'connected'
            elif line.startswith('_TOOL_RETRY_PARK_XY_T2'):
                self.position[:2] = [334., 168.]
                self.sensor_state = 'disconnected'
            elif line.startswith('G1 X'):
                self.position[0] = float(line.split()[1][1:])
            elif line.startswith('G1 Y'):
                self.position[1] = float(line.split()[1][1:])
            elif line == 'TOOLHEAD_PARK_OFF':
                self.aux.target_temp = 0.
            elif line.startswith('SET_FILAMENT_SENSOR'):
                self.switch_enabled = line.endswith('ENABLE=1')

    def test_standard_dock_uses_selected_geometry_and_no_auxiliary_commands(self):
        self.objects.pop('toolhead_auxiliary')
        self.objects.pop('heater_generic Toolhead')
        self.route.update(retry_x=263.5, retry_exit=(262., 257., 230.5))
        self.service.dock(self.gcmd)
        self.assertFalse(self.switch_enabled)
        self.assertIn('G1 X230.5 F1800', self.trace)
        self.service.manual_heat(self.gcmd, lambda _: self.nozzle.set_temp(220.))
        self.assertEqual(self.nozzle.target_temp, 220.)
        self.service.park(self.gcmd)
        self.assertTrue(self.switch_enabled)
        self.assertNotIn('TOOLHEAD_PARK_OFF', self.trace)
        self.assertFalse(self.service.get_status(0)['blocks_resume'])
        self.assertTrue(self.pause.is_paused)

    def test_unknown_route_never_moves(self):
        self.objects.pop('gcode_macro _TOOL_RETRY_PARK_XY_T2')
        with self.assertRaisesRegex(ValueError, '거치대 매크로'):
            self.service.dock(self.gcmd)
        self.assertEqual(self.trace, [])

    def test_unregistered_macro_does_not_enter_motion_hold(self):
        self.objects['gcode'].gcode_handlers.pop('_TOOL_RETRY_DOCK_XY_T2')
        with self.assertRaisesRegex(ValueError, '거치대 매크로'):
            self.service.dock(self.gcmd)
        self.assertEqual(self.trace, [])
        self.assertFalse(self.service.get_status(0)['blocks_resume'])

    def test_dock_heat_park_preserves_paused_job(self):
        self.service.dock(self.gcmd)
        self.assertEqual(self.position[:3], [0., 125., 25.])
        self.assertTrue(self.service.motion_locked())
        self.service.manual_heat(self.gcmd, lambda _: self.nozzle.set_temp(220.))
        self.assertEqual((self.nozzle.target_temp, self.aux.target_temp), (220., 220.))
        self.service.park(self.gcmd)
        self.assertTrue(self.pause.is_paused)
        self.assertEqual(self.position[:3], [0., 125., 25.])
        self.assertEqual((self.nozzle.target_temp, self.aux.target_temp), (0., 0.))
        self.assertEqual(self.saved['PAUSE_STATE']['last_position'], [7., 8., 20., 13.])
        self.assertFalse(self.service.get_status(0)['blocks_resume'])
        self.assertIn('_TOOL_RETRY_DOCK_XY_T2 APPROACH_F=20000', self.trace)
        park = '_TOOL_RETRY_PARK_XY_T2 APPROACH_F=20000'
        self.assertLess(self.trace.index('TOOLHEAD_PARK_OFF'), self.trace.index(park))
        self.assertEqual(self.trace.count('G1 X0 F20000'), 2)
        self.assertEqual(self.trace.count('G1 Y125 F20000'), 2)
        self.assertIn('G1 X366 F700', self.trace)

    def test_no_start_when_unpaused_unhomed_or_heating(self):
        self.pause.is_paused = False
        with self.assertRaises(ValueError):
            self.service.dock(self.gcmd)
        self.pause.is_paused = True
        self.homed = 'xy'
        with self.assertRaises(ValueError):
            self.service.dock(self.gcmd)
        self.homed = 'xyz'
        self.aux.last_pwm_value = .25
        with self.assertRaises(ValueError):
            self.service.dock(self.gcmd)
        self.assertEqual(self.trace, [])

    def test_failed_dock_stays_at_rack(self):
        self.dock_detects = False
        with self.assertRaises(ValueError):
            self.service.dock(self.gcmd)
        self.assertTrue(self.pause.is_paused)
        self.assertEqual(self.fast.phase, 'dock_sensor_hold')
        self.assertEqual(self.service.get_status(0)['phase'], 'fault')
        self.assertNotIn('G1 X0 F20000', self.trace)

    def test_lost_attachment_switches_heaters_off_without_movement(self):
        self.service.dock(self.gcmd)
        self.service.manual_heat(self.gcmd, lambda _: self.nozzle.set_temp(220.))
        self.sensor_state = 'disconnected'
        count = len(self.trace)
        self.service.watchdog(self.time)
        self.assertEqual((self.nozzle.target_temp, self.aux.target_temp), (0., 0.))
        self.assertEqual(len(self.trace), count)
        self.assertTrue(self.service.get_status(0)['blocks_resume'])
