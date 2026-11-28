import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance/toolhead_variant'))
from detachable_heater_sensor import DetachableHeaterSensor


class DockLinkRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.adapter = a = DetachableHeaterSensor.__new__(DetachableHeaterSensor)
        self.nozzle = NS(target_temp=225., set_temp=Mock())
        self.fast = NS(slot=1, requested=False, cleaning=False)
        self.time = 10.
        self.trace = []
        a.printer = NS(lookup_object=lambda name: NS(get_heater=lambda: self.nozzle))
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
        self.assertEqual(self.trace, ['_TOOL_RETRY_DOCK_XY_T2\nM400'] * 2)
        self.assertEqual(self.time, 12.)
        self.assertEqual(self.adapter.park_recovery_tool.call_count, 3)
        self.adapter.fault_wait_position.assert_called_once_with(self.fast)
        self.adapter.hold_dock.assert_called_once()

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
        self.assertEqual(self.trace, ['_TOOL_RETRY_DOCK_XY_T2\nM400'] * 2)
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

    def test_settle_before_exit_and_check_once_after_motion(self):
        a = self.adapter
        a.printer = NS(lookup_object=lambda name: self.fast if name == 'fast_cancel' else
                       NS(wait_moves=lambda: self.trace.append('moves drained')),
                       is_shutdown=lambda: False)
        self.fast.dock_abort = False
        a.dock_open_until = None
        a.dock_stage = 'prime'
        a.pause_at_dock = Mock()
        a.prime_complete(None)
        a.wait_dock_link.assert_called_once_with(self.fast, 'connected', 11.)
        self.assertEqual(a.dock_stage, 'exit')
        a.wait_dock_link.reset_mock()
        a.wait_dock_link.return_value = False
        a.verify_dock_exit(None)
        a.wait_dock_link.assert_called_once_with(self.fast, 'connected')
        self.assertEqual(self.trace, ['moves drained', 'moves drained'])
        a.pause_at_dock.assert_called_once()
        self.assertTrue(a.pause_at_dock.call_args.kwargs['at_exit'])

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
        self.adapter.wait_dock_link.side_effect = [True, True, False, False]
        self.assertFalse(self.recover())
        self.assertEqual(self.trace, ['_TOOL_RETRY_DOCK_XY_T2\nM400'])
        self.adapter.heater.set_temp.assert_not_called()
        self.adapter.hold_dock.assert_called_once()
