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
        self.assertEqual(self.trace, ['_T2_RETRY_DOCK_XY\nM400'] * 2)
        self.assertEqual(self.time, 12.)
        self.assertEqual(self.adapter.park_recovery_tool.call_count, 3)
        self.adapter.hold_dock.assert_called_once()

    def test_no_link_means_no_move(self):
        self.adapter.wait_dock_link.return_value = False
        self.assertFalse(self.recover())
        self.adapter.wait_dock_link.assert_called_once_with(self.fast, 'connected', 15.)
        self.adapter.park_recovery_tool.assert_not_called()
        self.assertEqual(self.trace, [])

    def test_incomplete_prime_can_park_without_replaying(self):
        self.adapter.dock_stage = 'prime'
        self.assertTrue(self.adapter.skip_interrupted_prime_line(['G1', 'E1']))
        self.assertFalse(self.adapter.skip_interrupted_prime_line(['TOOLHEAD_PRIME_COMPLETE']))
        self.assertFalse(self.recover(after_prime=True))
        self.adapter.park_recovery_tool.assert_called_once_with(None, self.fast, True)
        self.adapter.hold_dock.assert_called_once()
        self.assertEqual(self.trace, [])

    def test_unconfirmed_redock_stops_before_another_move(self):
        self.adapter.wait_dock_link.side_effect = [True, True, False]
        self.assertFalse(self.recover())
        self.assertEqual(self.trace, ['_T2_RETRY_DOCK_XY\nM400'])
        self.adapter.heater.set_temp.assert_not_called()
        self.adapter.hold_dock.assert_called_once()
