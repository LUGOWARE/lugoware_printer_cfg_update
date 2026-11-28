import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'maintenance'))
sys.path.insert(0, str(ROOT/'maintenance/toolhead_variant'))
from install_toolhead_variant import patch_ui
from lugo_dock_recovery import DockRecovery


def fast_class():
    import json
    source = ROOT/'maintenance/fast_cancel.py'
    ui = ROOT/'maintenance/toolhead_variant/ui_patches.json'
    edits = json.loads(ui.read_text(encoding='utf8'))['klipper/klippy/extras/fast_cancel.py']
    code = patch_ui(source.read_text(encoding='utf8'), edits, 'toolhead')
    scope = {'DockRecovery': DockRecovery}
    exec(compile(code.replace('from .lugo_dock_recovery import DockRecovery\n', ''),
                 str(source), 'exec'), scope)
    return scope['FastCancel']


class DockRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.pose = [367.5, 178.5, 4., 100.]
        self.mesh_z = 0.
        self.route = {'retry_x': 367.5, 'retry_y': 178.5, 'retry_exit': (366., 361., 334.5)}
        self.settings = {'homing_override': {'axes': 'z'},
                         'stepper_x': {'position_min': 0, 'position_max': 381}}
        self.sensor = 'disconnected'
        self.trace = []
        self.heater = NS(target_temp=0., last_pwm_value=0.)
        self.temps = NS(depth=0, changing=0)
        self.file = object()
        self.sd = NS(current_file=self.file, file_position=10, get_file_position=lambda: 20,
                     is_active=lambda: self.from_sd, is_cmd_from_sd=lambda: self.from_sd)
        self.from_sd = True
        self.registered = {}
        self.gcode = NS(register_command=self.registered.__setitem__, run_script_from_command=self.execute)
        self.pause = NS(is_paused=True)
        objs = {
            'toolhead': NS(get_status=lambda t: {
                'position': [*self.pose[:2], self.pose[2] + self.mesh_z, self.pose[3]],
                'homed_axes': 'xyz', 'axis_maximum': (381, 260, 370)}),
            'gcode_move': NS(get_status=lambda t: {'absolute_coordinates': True,
                                                  'gcode_position': self.pose, 'position': self.pose},
                             position_with_transform=lambda: self.pose,
                             saved_states={'PAUSE_STATE': {'last_position': self.pose.copy()}}),
            'toolhead_auxiliary': NS(get_status=lambda t: {'state': self.sensor}),
            'pause_resume': self.pause,
            'configfile': NS(get_status=lambda t: {'settings': self.settings}),
            'gcode_macro _TOOL_RETRY_DOCK_XY_T2': NS(get_status=lambda t: self.route),
            'lugo_tool_temperature': self.temps,
            'heater_generic Toolhead': self.heater,
            'extruder': NS(get_heater=lambda: self.heater),
        }
        self.printer = NS(lookup_object=objs.get, is_shutdown=lambda: False)
        cls = fast_class()
        self.fast = cls.__new__(cls)
        self.fast.__dict__.update(sd=self.sd, printer=self.printer, gcode=self.gcode,
                                  reactor=NS(monotonic=lambda: 0.), command_depth=0,
                                  dock_abort=False, requested=False, cleaning=False,
                                  phase='docking', slot=1, critical=True, inline_prime_skip=False)
        self.rec = self.fast.dock_recovery = DockRecovery(self.fast)
        self.fast.process = self.process
        self.command = NS(get_int=lambda name, default: 1, error=ValueError)
        self.fail_again = False

    def process(self, commands, need_ack):
        for line in commands:
            self.trace.append(line)
            if line == 'CHANGE_TOOL NEXT_TOOL=1':
                self.fast.process_commands(['DOCK_TOOL_1 EXTRUDER_TEMP=225', 'RESTORE_SPEED', 'ENABLE_SENSOR'])
            elif line == 'START_PRINT':
                self.fast.process_commands(['CHANGE_TOOL NEXT_TOOL=1', 'MESH_AUDIT'])
            elif line.startswith('DOCK_TOOL_1 '):
                self.fast.phase = 'docking'
                self.fast.process_commands(['PRE_DOCK', 'CHECK', 'HEAT', 'PRIME'])
            elif line == 'CHECK':
                if self.from_sd or self.fail_again:
                    self.pose[:3] = [self.route.get('retry_x', 367.5), 178.5, 4.]
                    self.rec.begin_hold(1)
                    self.fast.phase = 'dock_sensor_hold'
                    self.fast.dock_abort = True
                else:
                    self.fast.phase = 'docked'

    def execute(self, script):
        self.fast.process_commands(script.splitlines())

    def hold(self, line='CHANGE_TOOL NEXT_TOOL=1'):
        self.fast.process_commands([line])
        self.assertNotIn('HEAT', self.trace)
        self.assertNotIn('RESTORE_SPEED', self.trace)
        self.from_sd = False
        self.sd.file_position = 20
        self.assertTrue(self.rec.available())
        self.trace.clear()

    def test_home_defers_only_background_work_and_restores_timers_on_failure(self):
        now = [10.]
        seen = []

        def timer(module, name):
            def callback(eventtime):
                seen.append(name)
                now[0] += .010
                return eventtime + .25
            callback.__module__ = module
            callback.__qualname__ = name
            return NS(callback=callback)

        timers = [
            timer('extras.lugo_recovery', 'Recovery.tick'),
            timer('extras.exclude_tool_guard', 'ExcludeToolGuard.flush_pending'),
            timer('extras.paused_tool_service', 'PausedToolService.watchdog'),
            timer('webhooks', 'QueryStatusHelper._do_query'),
            timer('extras.verify_heater', 'HeaterCheck.check_event'),
            timer('extras.fast_cancel', 'FastCancel.request'),
            timer('extras.detachable_heater_sensor', 'DetachableSensor.watchdog'),
        ]
        original = [t.callback for t in timers]
        self.rec.reactor._timers = timers
        self.rec.reactor.monotonic = lambda: now[0]

        def run(script):
            self.assertEqual(script, 'G28 X Y\nM400')
            for t in timers:
                self.assertGreater(t.callback(10.), 10.)
            raise ValueError('home failed')

        self.gcode.run_script_from_command = run
        with self.assertLogs(level='INFO') as logs:
            with self.assertRaisesRegex(ValueError, 'home failed'):
                self.rec.home_xy()
        self.assertEqual(seen, [fn.__qualname__ for fn in original[2:]])
        self.assertEqual([t.callback for t in timers], original)
        self.assertIn("'deferred': 1", logs.output[0])
        self.assertIn("'calls': 1", logs.output[0])
        for t in timers[:2]:
            t.callback(now[0])
        self.assertEqual(seen[-2:], [fn.__qualname__ for fn in original[:2]])

    def test_continues_first_dock_before_advancing_sd(self):
        self.hold('START_PRINT')
        def process(commands, need_ack):
            for line in commands:
                if line == 'YES':
                    self.rec.resume(self.command)
                else:
                    self.process([line], need_ack)
        self.fast.process = process
        self.fast.process_commands(['YES'])
        self.assertLess(self.trace.index('G1 X0 F3600'), self.trace.index('G28 X Y'))
        self.assertLess(self.trace.index('G28 X Y'), self.trace.index('HEAT'))
        self.assertLess(self.trace.index('PRIME'), self.trace.index('RESTORE_SPEED'))
        self.assertLess(self.trace.index('ENABLE_SENSOR'), self.trace.index('MESH_AUDIT'))
        self.assertLess(self.trace.index('MESH_AUDIT'), self.trace.index('BASE_RESUME'))
        self.assertFalse(self.rec.available())
        self.assertEqual((self.temps.depth, self.temps.changing), (0, 0))

    def test_uses_the_selected_model_route(self):
        self.route = {'retry_x': 263.5, 'retry_y': 178.5, 'retry_exit': (262., 257., 230.5)}
        self.settings['stepper_x']['position_max'] = 277
        self.hold()
        self.rec.resume(self.command)
        self.assertIn('G1 X257 F700', self.trace)
        self.assertIn('G1 X230.5 F1800', self.trace)
        self.assertNotIn('G1 X361 F700', self.trace)
        self.assertIn('BASE_RESUME', self.trace)

    def test_confirms_parked_tool_and_replays_at_x0_after_x_home(self):
        self.hold()
        self.pose[0] = 0.
        self.mesh_z = .32
        self.rec.resume(self.command)
        self.assertEqual([line for line in self.trace if line.startswith('G1 X')], [])
        self.assertLess(self.trace.index('G28 X Y'), self.trace.index('HEAT'))
        self.assertLess(self.trace.index('PRIME'), self.trace.index('ENABLE_SENSOR'))
        self.assertLess(self.trace.index('ENABLE_SENSOR'), self.trace.index('BASE_RESUME'))
        self.assertFalse(self.rec.available())

    def test_resumes_from_verified_x10_y125_only(self):
        self.hold()
        self.pose[:2] = [10., 125.]
        self.rec.record.update(returned=True, position=tuple(self.pose[:3]))
        self.pose[1] += 1.
        with self.assertRaisesRegex(ValueError, 'X10 Y125'):
            self.rec.resume(self.command)
        self.assertEqual(self.trace, [])
        self.pose[1] = 125.
        self.rec.resume(self.command)
        self.assertEqual([line for line in self.trace if line.startswith('G1 X')], [])
        self.assertLess(self.trace.index('G28 X Y'), self.trace.index('HEAT'))
        self.assertIn('BASE_RESUME', self.trace)

    def test_x0_does_not_bypass_saved_position_or_sensor_checks(self):
        self.hold()
        self.pose[0] = 0.
        original_pose = self.pose.copy()
        for axis, value in ((1, 125.), (2, 5.)):
            self.pose[axis] = value
            with self.assertRaises(ValueError):
                self.rec.resume(self.command)
            self.pose[:] = original_pose
        self.sensor = 'connected'
        with self.assertRaises(ValueError):
            self.rec.resume(self.command)
        self.sensor = 'disconnected'
        self.rec.record['position'] = (100., 178.5, 4.)
        with self.assertRaisesRegex(ValueError, 'saved tool position'):
            self.rec.resume(self.command)
        self.assertEqual(self.trace, [])

    def test_mesh_compensation_during_xy_travel_is_allowed(self):
        self.hold()
        self.mesh_z = .32
        self.rec.require_safe(self.command, self.rec.record, at_dock=False)
        self.pose[2] += .32
        with self.assertRaises(ValueError):
            self.rec.require_safe(self.command, self.rec.record, at_dock=False)

    def test_print_disconnection_needs_an_inactive_sd_file_and_safe_height(self):
        self.settings['gcode_macro resume_action_t1'] = {}
        self.pause.sd_paused = True
        self.rec.begin_print_hold(1, (230., 230.))
        self.assertIsNone(self.rec.record)
        self.from_sd = False
        self.fast.phase = 'dock_sensor_hold'
        self.rec.begin_print_hold(1, (230., 230.))
        self.assertTrue(self.rec.available())
        self.assertEqual(self.rec.record['offset'], self.sd.file_position)
        self.assertEqual(self.rec.record['kind'], 'print')
        last_position = self.rec.record['pause_state']['last_position']
        self.pose[2] = 367.
        self.assertEqual(last_position[2], 4.)
        self.rec.record = None
        self.rec.begin_print_hold(1, (230., 230.))
        self.assertIsNone(self.rec.record)

    def test_unknown_route_cannot_resume(self):
        self.route = {}
        self.fast.process_commands(['CHANGE_TOOL NEXT_TOOL=1'])
        self.from_sd = False
        self.sd.file_position = 20
        self.assertFalse(self.rec.available())
        with self.assertRaises(ValueError):
            self.rec.resume(self.command)
        self.assertNotIn('G28 X Y', self.trace)

    def test_never_moves_for_missing_confirmation_or_changed_sensor(self):
        self.hold()
        with self.assertRaises(ValueError):
            self.rec.resume(NS(get_int=lambda *args: 0, error=ValueError))
        self.sensor = 'connected'
        with self.assertRaises(ValueError):
            self.rec.resume(self.command)
        self.assertEqual(self.trace, [])

    def test_no_motion_with_changed_job_position_or_heater(self):
        self.hold()
        self.sd.file_position = 21
        with self.assertRaises(ValueError):
            self.rec.resume(self.command)
        self.sd.file_position = 20
        self.heater.last_pwm_value = .25
        with self.assertRaises(ValueError):
            self.rec.resume(self.command)
        self.heater.last_pwm_value = 0.
        self.pose[0] = 25.
        with self.assertRaises(ValueError):
            self.rec.resume(self.command)
        self.assertEqual(self.trace, [])

    def test_repeat_fault_keeps_original_continuation_paused(self):
        self.hold()
        self.fail_again = True
        self.fast.process = lambda commands, need_ack: (
            [self.rec.resume(self.command) if line == 'YES' else self.process([line], need_ack)
             for line in commands])
        self.fast.process_commands(['YES'])
        self.assertNotIn('BASE_RESUME', self.trace)
        self.assertNotIn('HEAT', self.trace)
        self.assertTrue(self.rec.available())
        self.assertIn('RESTORE_SPEED', self.rec.record['continuation'][0])
        with self.assertRaises(ValueError):
            self.rec.resume(self.command)  # Earlier confirmation expired.


if __name__ == '__main__':
    unittest.main()
