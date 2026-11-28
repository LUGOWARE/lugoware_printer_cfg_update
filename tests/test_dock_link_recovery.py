import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance/toolhead_variant'))
from detachable_heater_sensor import DetachableHeaterSensor
from lugo_dock_recovery import DockRecovery


class DockLinkRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.adapter = a = DetachableHeaterSensor.__new__(DetachableHeaterSensor)
        self.nozzle = NS(target_temp=225., set_temp=Mock())
        self.fast = NS(slot=1, requested=False, cleaning=False)
        self.time = 10.
        self.trace = []
        a.printer = NS(lookup_object=lambda name: NS(get_heater=lambda: self.nozzle),
                       is_shutdown=lambda: False)
        a.source = NS(reactor=NS(monotonic=lambda: self.time, pause=self.pause),
                      gcode=NS(error=ValueError, respond_info=Mock(),
                               run_script_from_command=self.trace.append))
        a.heater = NS(set_temp=Mock())
        a.dock_open_until = 15.
        a.dock_stage = 'preheat'
        a.dock_retries = 0
        a.prime_incomplete = False
        a.wait_dock_link = Mock(return_value=True)
        a.park_recovery_tool = Mock(return_value=True)
        a.hold_dock = Mock()
        a.fault_wait_position = Mock(return_value=True)
        a.log_dock_block = Mock()
        a.home_before_redock = Mock(side_effect=lambda fast: self.trace.append("G28 X Y") is None)

    def pause(self, deadline):
        self.time = deadline
        return deadline

    def recover(self, after_prime=False):
        return self.adapter.recover_dock(None, self.fast, 220., after_prime)

    def test_two_retries_then_park_and_pause(self):
        for _ in range(2):
            self.adapter.dock_open_until = self.time + 5.
            self.assertTrue(self.recover())
        self.adapter.dock_open_until = self.time + 5.
        self.assertFalse(self.recover())
        self.assertEqual(self.trace, ['_TOOL_RETRY_DOCK_XY_T2\nM400', 'G28 X Y', '_TOOL_RETRY_DOCK_XY_T2\nM400'])
        self.assertEqual(self.time, 11.)
        self.assertEqual(self.adapter.park_recovery_tool.call_count, 3)
        self.adapter.fault_wait_position.assert_called_once_with(self.fast)
        self.adapter.hold_dock.assert_called_once()

    def test_second_redock_stops_when_link_changes_during_home(self):
        a = self.adapter
        a.dock_retries = 1
        can_move = Mock(side_effect=[True, False])
        self.assertFalse(a.redock_parked_tool(self.fast, can_move))
        a.home_before_redock.assert_called_once_with(self.fast)
        self.assertEqual(self.trace, ['G28 X Y'])
        self.assertEqual(a.dock_retries, 1)

    def test_second_redock_home_requires_clear_rack_and_confirmed_origin(self):
        a = self.adapter
        del a.home_before_redock
        a.heater = NS(target_temp=0., last_pwm_value=0.)
        self.nozzle.target_temp = self.nozzle.last_pwm_value = 0.
        position = [334., 168., 2.]
        head = NS(get_status=lambda _: {
            'position': position.copy(), 'homed_axes': 'xyz',
            'axis_minimum': (-2., -2., 0.), 'axis_maximum': (381., 257., 375.)})
        mover = NS(get_status=lambda _: {'absolute_coordinates': True,
                                        'gcode_position': position.copy()})
        config = NS(get_status=lambda _: {'settings': {
            'printer': {'kinematics': 'cartesian'}, 'homing_override': {'axes': 'z'},
            'stepper_x': {'position_endstop': 0.}, 'stepper_y': {'position_endstop': 255.}}})
        route = NS(get_status=lambda _: {'retry_exit': (366., 361., 334.5)})
        a.printer.lookup_object = {
            'toolhead': head, 'gcode_move': mover, 'configfile': config,
            'extruder': NS(get_heater=lambda: self.nozzle),
            'gcode_macro _TOOL_RETRY_DOCK_XY_T2': route,
        }.__getitem__
        home = Mock()
        self.fast.dock_recovery = NS(home_xy=home)
        position[0] = 367.5
        self.assertFalse(a.home_before_redock(self.fast))
        home.assert_not_called()
        position[0] = 334.
        self.assertFalse(a.home_before_redock(self.fast))
        home.assert_called_once()
        unknown_calls = []
        callback = unknown_calls.append
        self.assertIsNone(callback.__module__)
        timer = NS(callback=callback)
        recovery = DockRecovery.__new__(DockRecovery)
        recovery.reactor = a.source.reactor
        recovery.reactor._timers = [timer]
        recovery.gcode = a.source.gcode
        self.fast.dock_recovery = recovery
        a.dock_retries = 1

        def run(script):
            self.trace.append(script)
            if script.startswith('G28'):
                self.assertIs(timer.callback, callback)
                timer.callback(self.time)
                position[:2] = [0., 255.]

        recovery.gcode.run_script_from_command = run
        self.assertTrue(a.redock_parked_tool(self.fast, lambda: True))
        self.assertEqual(self.trace, ['G28 X Y\nM400', '_TOOL_RETRY_DOCK_XY_T2\nM400'])
        self.assertEqual(a.dock_retries, 2)
        self.assertEqual(unknown_calls, [self.time])
        self.assertIs(timer.callback, callback)

    def test_no_link_checks_return_without_attempting_parking(self):
        self.adapter.wait_dock_link.return_value = False
        self.assertFalse(self.recover())
        self.assertEqual([call.args[1] for call in self.adapter.wait_dock_link.call_args_list],
                         ['connected', 'disconnected'])
        self.adapter.park_recovery_tool.assert_not_called()
        self.adapter.fault_wait_position.assert_called_once_with(self.fast)
        self.assertEqual(self.trace, [])

    def test_preprime_disconnected_retries_twice_without_heating(self):
        self.adapter.wait_dock_link.side_effect = lambda fast, state, deadline=None: state == 'disconnected'
        self.assertFalse(self.recover())
        self.assertEqual(self.trace, ['_TOOL_RETRY_DOCK_XY_T2\nM400', 'G28 X Y', '_TOOL_RETRY_DOCK_XY_T2\nM400'])
        self.assertEqual(self.adapter.park_recovery_tool.call_count, 2)
        self.assertTrue(self.adapter.park_recovery_tool.call_args.kwargs['allow_disconnected'])
        self.adapter.heater.set_temp.assert_not_called()
        self.nozzle.set_temp.assert_called_once_with(0.)
        self.adapter.hold_dock.assert_called_once()

    def test_retry_exhaustion_executes_real_diagnostic_before_hold(self):
        a = self.adapter
        self.fast.phase = 'docking'
        a.dock_retries = 1
        a.wait_dock_link.return_value = False
        a.valid_samples = 0
        a.source.get_status = Mock(return_value={'state': 'disconnected', 'temperature': None})
        head = NS(get_status=lambda now: {'homed_axes': 'xyz', 'position': [367.5, 178.5, 2.]})
        a.printer.lookup_object = lambda name: (head if name == 'toolhead' else
                                               NS(get_heater=lambda: self.nozzle))
        self.nozzle.last_pwm_value = 0.
        a.heater.target_temp = a.heater.last_pwm_value = 0.
        del a.log_dock_block
        with self.assertLogs(level='INFO') as caught:
            self.assertFalse(self.recover())
        self.assertIn('retries=1 sensor=disconnected', caught.output[0])
        a.hold_dock.assert_called_once()
        a.hold_dock.reset_mock()
        a.source.get_status.side_effect = RuntimeError('diagnostic missing')
        with self.assertLogs(level='ERROR') as caught:
            self.assertFalse(self.recover())
        self.assertIn('Unable to collect toolhead recovery diagnostics', caught.output[0])
        a.hold_dock.assert_called_once()

    def test_incomplete_prime_can_park_without_replaying(self):
        self.adapter.dock_stage = 'prime'
        self.assertTrue(self.adapter.skip_interrupted_prime_line(['G1', 'E1']))
        self.assertFalse(self.adapter.skip_interrupted_prime_line(['TOOLHEAD_PRIME_COMPLETE']))
        self.assertFalse(self.recover(after_prime=True))
        self.adapter.park_recovery_tool.assert_called_once_with(None, self.fast, True)
        self.adapter.hold_dock.assert_called_once()
        self.assertEqual(self.trace, [])

    def prepare_nominal_exit(self):
        a = self.adapter
        self.markers = []
        self.fast.dock_abort = False
        self.fast.phase = 'docked'
        self.fast.sd = NS(must_pause_work=False, is_active=lambda: False,
                          is_cmd_from_sd=lambda: False)
        self.head = NS(wait_moves=Mock(), register_lookahead_callback=self.markers.append)
        self.pause = NS(sd_paused=False, pause_command_sent=False)
        objects = {'toolhead': self.head, 'fast_cancel': self.fast, 'pause_resume': self.pause}
        a.printer = NS(lookup_object=objects.get, is_shutdown=lambda: False)
        a.context = lambda now: (1, 'printing', 'job', self.fast.requested)
        a.heater.target_temp = 220.
        a.heater.mcu_pwm = NS(get_mcu=lambda: NS(estimated_print_time=lambda now: now))
        a.nozzle_heater = self.nozzle
        a.original_set_temp = Mock()
        a.dock_exit = None
        a.pending_print_fault = None
        a.source.reactor.register_callback = Mock()
        a.dock_open_until = None
        a.dock_stage = 'prime'
        return a

    def test_healthy_prime_and_exit_never_drain_or_wait_at_rack(self):
        a = self.prepare_nominal_exit()
        a.prime_complete(None)
        self.assertEqual(a.dock_stage, 'exit')
        a.verify_dock_exit(None)
        self.assertEqual(len(self.markers), 1)
        self.head.wait_moves.assert_not_called()
        self.assertEqual(self.time, 10.)
        self.markers[0](12.)
        self.assertFalse(a.watch_dock_exit(11.9))
        self.assertEqual(a.dock_stage, 'exit')
        self.assertFalse(a.watch_dock_exit(12.))
        self.assertIsNone(a.dock_exit)
        self.assertFalse(self.fast.sd.must_pause_work)
        self.assertIsNone(a.pending_print_fault)

    def test_exit_sensor_fault_stops_sd_and_preserves_resume_owner(self):
        a = self.prepare_nominal_exit()
        a.prime_complete(None)
        a.verify_dock_exit(None)
        self.markers[0](12.)
        a.dock_open_until = 15.
        self.assertTrue(a.watch_dock_exit(10.2))
        self.assertTrue(self.fast.sd.must_pause_work)
        a.original_set_temp.assert_called_once_with(0.)
        self.nozzle.set_temp.assert_called_once_with(0.)
        a.source.reactor.register_callback.assert_called_once()
        a.context = lambda now: (1, 'paused', 'job', False)
        a.fault_pause(None)
        self.assertTrue(self.pause.sd_paused)
        self.assertTrue(self.pause.pause_command_sent)
        self.assertEqual(a.hold_dock.call_args.kwargs['print_fault'], (1, (225., 220.)))

    def test_raw_open_sample_shuts_heaters_and_stops_queue_before_exit_marker(self):
        a = self.prepare_nominal_exit()
        a.heater.set_pwm = Mock()
        a.prime_complete(None)
        a.verify_dock_exit(None)
        self.assertIsNone(a.dock_exit['time'])
        a.detached(10.1)
        a.heater.set_pwm.assert_called_once_with(10.1, 0.)
        self.assertTrue(self.fast.sd.must_pause_work)
        a.source.reactor.register_callback.assert_called_once()
        self.markers[0](12.)
        self.assertIsNone(a.dock_exit)

    def test_cancel_before_exit_completion_discards_obsolete_marker(self):
        a = self.prepare_nominal_exit()
        a.prime_complete(None)
        a.verify_dock_exit(None)
        self.fast.requested = True
        self.assertFalse(a.watch_dock_exit(11.))
        self.markers[0](12.)
        self.assertIsNone(a.dock_exit)
        a.hold_dock.assert_not_called()
        self.assertFalse(self.fast.sd.must_pause_work)

    def test_already_bad_exit_still_waits_and_uses_dock_pause(self):
        a = self.prepare_nominal_exit()
        a.prime_complete(None)
        a.wait_dock_link.return_value = False
        a.pause_at_dock = Mock()
        a.verify_dock_exit(None)
        self.head.wait_moves.assert_called_once()
        a.pause_at_dock.assert_called_once()
        self.assertTrue(a.pause_at_dock.call_args.kwargs['at_exit'])
        self.assertEqual(self.markers, [])

    def test_unstable_sensor_holds_before_exit(self):
        a = self.adapter
        a.printer = NS(lookup_object=lambda name: self.fast if name == 'fast_cancel' else
                       NS(wait_moves=Mock()), is_shutdown=lambda: False)
        self.fast.dock_abort = False
        a.dock_open_until = None
        a.dock_stage = 'prime'
        a.pause_at_dock = Mock()
        a.wait_dock_link.return_value = False
        a.prime_complete(None)
        a.pause_at_dock.assert_called_once()
        self.assertTrue(a.pause_at_dock.call_args.kwargs["after_prime"])
        self.assertNotEqual(a.dock_stage, 'exit')

    def test_pause_parks_attached_tool_before_returning(self):
        a = self.adapter
        self.fast.phase = 'docking'
        a.printer.is_shutdown = lambda: False
        a.pause_at_dock(None, self.fast, 'test')
        a.park_recovery_tool.assert_called_once()
        a.fault_wait_position.assert_called_once_with(self.fast)
        self.assertTrue(a.hold_dock.call_args.kwargs['returned'])

    def test_pause_checks_return_for_either_attachment_state(self):
        a = self.adapter
        a.printer.is_shutdown = lambda: False
        a.wait_dock_link.side_effect = lambda fast, state: state == 'disconnected'
        self.fast.phase = 'docking'
        a.pause_at_dock(None, self.fast, 'test')
        a.park_recovery_tool.assert_not_called()
        a.fault_wait_position.assert_called_once_with(self.fast)
        a.fault_wait_position.reset_mock()
        a.log_dock_block.assert_called_once()
        self.fast.phase = 'empty'
        a.pause_at_dock(None, self.fast, 'test')
        a.park_recovery_tool.assert_not_called()
        a.fault_wait_position.assert_called_once_with(self.fast)

    def test_second_failure_uses_verified_exit_without_sensor_or_third_redock(self):
        a = self.adapter
        a.dock_retries = 2
        a.wait_dock_link.return_value = False
        a.fault_wait_position.return_value = True
        self.assertFalse(self.recover())
        a.park_recovery_tool.assert_not_called()
        self.assertEqual(self.trace, [])
        a.hold_dock.assert_called_once()
        self.assertTrue(a.hold_dock.call_args.kwargs['returned'])

    def test_return_uses_verified_rack_exit_and_lowers_bed_only_on_cancel(self):
        a = self.adapter
        del a.fault_wait_position
        a.failed = False
        a.heater.target_temp = 0.
        self.nozzle.target_temp = 0.
        a.printer.is_shutdown = lambda: False
        pos = [367.5, 178.5, 372.]
        route = {'retry_x': 367.5, 'retry_y': 178.5, 'retry_exit': (366., 361., 334.5)}
        head = NS(wait_moves=Mock(), get_status=lambda _: {
            'position': pos, 'homed_axes': 'xyz',
            'axis_minimum': (0., 0., 0.), 'axis_maximum': (381., 260., 375.)})
        objects = {'toolhead': head,
                   'gcode_move': NS(get_status=lambda _: {'gcode_position': pos}),
                   'gcode_macro _TOOL_RETRY_DOCK_XY_T2': NS(get_status=lambda _: route),
                   'extruder': NS(get_heater=lambda: self.nozzle)}
        a.printer.lookup_object = objects.get
        a.wait_dock_link.side_effect = AssertionError('Return must not depend on attachment')
        self.assertTrue(a.fault_wait_position(self.fast))
        steps = ['G90', 'G1 X366 F700', 'G1 X361 F700', 'G1 X334.5 F1800']
        to_wait = ['G1 X10 F6000', 'G1 Y125 F6000']
        self.assertEqual(self.trace, [step + '\nM400' for step in steps + to_wait])
        self.trace.clear()
        self.fast.requested = True
        self.assertTrue(a.fault_wait_position(self.fast, lower_bed=True))
        lift = ['G91\nG1 Z3.0000 F600\nG90']
        self.assertEqual(self.trace, [step + '\nM400' for step in steps + lift + to_wait])
        self.trace.clear()
        pos[0] = 370.
        self.assertFalse(a.fault_wait_position(self.fast, lower_bed=True))
        self.assertEqual(self.trace, [])

    def test_protected_sensor_faults_still_stop_heating(self):
        for state, temp, power, last_active in (
                ('connected', -8.2, 0., 9.),
                ('short_circuit', None, .4, None),
                ('connected', 301., 0., None)):
            with self.subTest(state=state, temp=temp):
                a = self.adapter
                a.failed = False
                a.last_active = last_active
                a.minimum, a.maximum = 0., 300.
                a.heater = NS(target_temp=0., last_pwm_value=power, set_temp=Mock())
                a.printer.invoke_shutdown = Mock()
                a.sample(self.time, state, temp)
                a.heater.set_temp.assert_called_once_with(0.)
                a.printer.invoke_shutdown.assert_called_once()
                self.assertEqual(self.trace, [])

    def test_unconfirmed_redock_stops_before_another_move(self):
        self.adapter.wait_dock_link.side_effect = [True, True, True, False, False]
        self.assertFalse(self.recover())
        self.assertEqual(self.trace, ['_TOOL_RETRY_DOCK_XY_T2\nM400'])
        self.adapter.heater.set_temp.assert_not_called()
        self.adapter.hold_dock.assert_called_once()
