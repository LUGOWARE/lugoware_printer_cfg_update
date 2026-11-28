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
        a.fault_wait_position = Mock()

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

    def test_no_link_means_no_move(self):
        self.adapter.wait_dock_link.return_value = False
        self.assertFalse(self.recover())
        self.assertEqual([call.args[1] for call in self.adapter.wait_dock_link.call_args_list],
                         ['connected', 'disconnected'])
        self.adapter.park_recovery_tool.assert_not_called()
        self.adapter.fault_wait_position.assert_not_called()
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
        a.wait_dock_link.return_value = False
        a.prime_complete(None)
        a.hold_dock.assert_called_once()
        self.assertNotEqual(a.dock_stage, 'exit')

    def test_unconfirmed_redock_stops_before_another_move(self):
        self.adapter.wait_dock_link.side_effect = [True, True, False, False]
        self.assertFalse(self.recover())
        self.assertEqual(self.trace, ['_TOOL_RETRY_DOCK_XY_T2\nM400'])
        self.adapter.heater.set_temp.assert_not_called()
        self.adapter.hold_dock.assert_called_once()
