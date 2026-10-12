import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maintenance"))
import unittest
from types import SimpleNamespace as Obj
from contextlib import nullcontext
from lugo_fast_cancel import FastCancel, MeshCancelled


class Tests(unittest.TestCase):
    def setup_mesh(self):
        self.obj.printing = lambda: True
        self.obj.mesh_active = False
        self.obj.mesh_helper = Obj(_raise_tool=lambda: self.log.append('lift'))
        def end():
            self.assertTrue(self.obj.mesh_active)
            self.log.append('end_session')
            self.obj.mesh_probe.hw_probe_session = None
        self.obj.mesh_probe = Obj(hw_probe_session=object(), end_probe_session=end)
        self.obj.mesh_next = lambda point: self.log.append('next')
        self.obj.mesh_finalize = lambda results: self.log.append('save')
        self.obj.mesh_sample = lambda cmd: self.log.append('sample')
        self.cmd = Obj(get=lambda key, default=None: default)

    def test_mesh_cancel_after_current_sample_discards_results(self):
        self.setup_mesh()
        self.obj.requested = False
        def sample(cmd):
            self.log.append('probe_finished')
            self.obj.requested = True
        self.obj.mesh_sample = sample
        def start(cmd):
            self.obj.probe_sample(cmd)
            self.obj.mesh_move_next(1)
            self.obj.finalize_mesh([])
        self.obj.mesh_start = start
        self.obj.start_mesh(self.cmd)
        self.assertEqual(self.log, ['probe_finished', 'lift', 'end_session'])
        self.assertFalse(self.obj.mesh_active)

    def test_mesh_cancellation_prevents_next_point_and_publish(self):
        self.setup_mesh()
        self.obj.mesh_active = True
        for call in (lambda: self.obj.mesh_move_next(1), lambda: self.obj.finalize_mesh([])):
            with self.assertRaises(MeshCancelled):
                call()
        self.assertEqual(self.log, [])

    def test_probe_cleanup_gcode_is_not_filtered(self):
        self.obj.mesh_active = True
        self.obj.process = lambda lines, ack: list(lines)
        self.assertEqual(self.obj.process_commands(['Probe_Stow', 'SET_PIN PIN=probe_enable VALUE=0']),
                         ['Probe_Stow', 'SET_PIN PIN=probe_enable VALUE=0'])

    def test_normal_mesh_and_probe_errors_preserved(self):
        self.setup_mesh()
        self.obj.requested = False
        self.obj.mesh_start = lambda cmd: self.obj.probe_sample(cmd)
        self.obj.start_mesh(self.cmd)
        self.assertEqual(self.log, ['sample'])
        def fail(cmd):
            raise ValueError('probe failure')
        self.obj.mesh_sample = fail
        with self.assertRaisesRegex(ValueError, 'probe failure'):
            self.obj.start_mesh(self.cmd)
        self.assertFalse(self.obj.mesh_active)

    def setUp(self):
        self.obj = FastCancel.__new__(FastCancel)
        self.obj.requested = True
        self.obj.cleaning = self.obj.critical = False
        self.obj.phase = 'normal'
        self.obj.slot = -1
        self.obj.message = ''
        self.log = []
        self.mounted = True
        self.homed = 'xyz'
        self.active = 0
        self.obj.reactor = Obj(monotonic=lambda: 0, pause=lambda t: t)
        self.obj.sd = Obj(work_timer=None, do_cancel=lambda: self.log.append('cancel'))
        self.obj.heaters = Obj(turn_off_all_heaters=lambda: self.log.append('off'))
        def script(s):
            self.log.append(s)
            if 'PARK_TOOL_' in s:
                self.mounted = False
        self.obj.gcode = Obj(get_mutex=nullcontext, run_script_from_command=script,
                             respond_info=self.log.append, error=ValueError,
                             create_gcode_command=lambda *a: None)
        self.objects = {
            'toolhead': Obj(wait_moves=lambda: None, get_status=lambda t: {'homed_axes': self.homed, 'axis_maximum': [300, 300, 300]}, get_position=lambda: [100, 100, 20]),
            'filament_switch_sensor toolhead_sensor': Obj(get_status=lambda t: {'filament_detected': self.mounted}),
            'gcode_macro TOOL_STATE': Obj(get_status=lambda t: {'active_tool': self.active}),
            'pause_resume': Obj(cmd_CANCEL_PRINT=lambda c: None),
        }
        self.obj.printer = Obj(lookup_object=lambda n, default=None: self.objects.get(n, default), is_shutdown=lambda: False)

    def test_mounted_original_tool_parks(self):
        self.obj.finish(0)
        self.assertTrue(any('PARK_TOOL_0' in s for s in self.log))
        self.assertEqual(self.log[-2:], ['off', 'cancel'])

    def test_newly_attached_slot_overrides_stale_number(self):
        self.obj.phase, self.obj.slot = 'docked', 3
        self.obj.finish(0)
        self.assertTrue(any('PARK_TOOL_3' in s for s in self.log))
        self.assertFalse(any('PARK_TOOL_0' in s for s in self.log))

    def test_already_parked_does_not_park_twice(self):
        self.obj.phase, self.mounted = 'empty', False
        self.obj.finish(0)
        self.assertFalse(any('PARK_TOOL_' in s for s in self.log))

    def test_mismatch_and_unhomed_do_not_move(self):
        for phase, homed in [('empty', 'xyz'), ('normal', '')]:
            self.setUp()
            self.obj.phase, self.homed = phase, homed
            self.obj.finish(0)
            self.assertFalse(any('G1 ' in s for s in self.log))
            self.assertIn('off', self.log)
            self.assertIn('cancel', self.log)

    def test_remaining_macro_lines_are_skipped(self):
        self.obj.process = lambda lines, ack: list(lines)
        self.assertEqual(self.obj.process_commands(['G1 X10', 'G1 X20']), [])
        self.assertEqual(self.obj.process_commands(['M112']), ['M112'])

    def test_critical_segment_finishes_only_to_boundary(self):
        self.obj.critical = True
        def process(lines, ack):
            result = []
            for line in lines:
                result.append(line)
                if line == 'SAFE_POINT':
                    self.obj.critical = False
            return result
        self.obj.process = process
        self.assertEqual(self.obj.process_commands(['LATCH', 'SAFE_POINT', 'NEXT_TOOL']), ['LATCH', 'SAFE_POINT'])

    def test_normal_commands_unchanged(self):
        self.obj.requested = False
        self.obj.process = lambda lines, ack: list(lines)
        self.assertEqual(self.obj.process_commands(['G1 X10']), ['G1 X10'])

    def test_wait_exits_without_faking_temperature(self):
        self.obj.printer.get_start_args = lambda: {}
        self.obj.wait_heater(Obj(check_busy=lambda t: True))
        self.assertEqual(self.log, [])

    def test_restart_commands_pass_pending_cancel(self):
        self.obj.process = lambda lines, ack: list(lines)
        for cmd in ('RESTART', 'FIRMWARE_RESTART', 'firmware_restart ; reset', 'M112'):
            self.assertEqual(self.obj.process_commands([cmd]), [cmd])

    def test_shutdown_abandons_recovery_without_motion(self):
        self.obj.shutdown()
        self.obj.finish(0)
        self.assertFalse(self.obj.requested)
        self.assertEqual(self.log, [])

    def test_shutdown_does_not_wait_for_sd_worker(self):
        self.obj.printer.is_shutdown = lambda: True
        self.obj.sd.work_timer = object()
        self.obj.finish(0)
        self.assertEqual(self.log, [])

    def test_cancel_wait_flushes_only_once(self):
        self.obj.requested = False
        self.obj.printing = lambda: True
        time = [0.]
        flushes = []
        self.objects['toolhead'].wait_moves = lambda: flushes.append(1)
        def pause(t):
            time[0] = t
            return t
        self.obj.reactor = Obj(monotonic=lambda: time[0], pause=pause)
        self.obj.dwell(Obj(get_float=lambda *a, **kw: 1000))
        self.assertEqual(flushes, [1])
        self.assertAlmostEqual(time[0], 1.)

    def test_cancel_wait_breaks_early(self):
        self.obj.requested = False
        self.obj.printing = lambda: True
        def pause(t):
            self.obj.requested = True
            return t
        self.obj.reactor = Obj(monotonic=lambda: 0., pause=pause)
        self.obj.dwell(Obj(get_float=lambda *a, **kw: 20000))
        self.assertTrue(self.obj.requested)


if __name__ == '__main__':
    unittest.main()
