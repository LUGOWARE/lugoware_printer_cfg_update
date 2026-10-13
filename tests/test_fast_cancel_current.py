import sys, unittest
from pathlib import Path
from types import SimpleNamespace as Obj
from contextlib import nullcontext
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"maintenance"))
from fast_cancel import FastCancel, MeshCancelled

class Tests(unittest.TestCase):
    def test_finish_delegates_motion_and_finalization_to_cfg(self):
        self.obj.phase, self.obj.slot = 'docked', 2
        self.obj.prime_skipped = True
        self.obj.finish(0)
        self.assertEqual(self.log, ['_FAST_CANCEL_MOTION TOOL=2 SKIP_EXTRUDE=1',
                                   '_FAST_CANCEL_FINALIZE', 'off', 'cancel'])
        self.assertFalse(self.obj.requested)
        self.assertFalse(self.obj.cleaning)

    def test_cfg_failure_still_turns_heaters_off_and_cancels(self):
        def fail(script):
            self.log.append(script)
            raise ValueError('test macro failure')
        self.obj.gcode.run_script_from_command = fail
        self.obj.finish(0)
        self.assertIn('_FAST_CANCEL_FINALIZE', self.log)
        self.assertEqual(self.log[-2:], ['off', 'cancel'])
        self.assertFalse(self.obj.requested)

    def test_unhomed_axes_skip_motion_but_finalize(self):
        self.homed = 'xy'
        self.obj.finish(0)
        self.assertFalse(any(s.startswith('_FAST_CANCEL_MOTION') for s in self.log))
        self.assertEqual(self.log[-3:], ['_FAST_CANCEL_FINALIZE', 'off', 'cancel'])

    def offset(self, initial, final):
            self.objects['gcode_macro Z_OFFSET_TRACKER'] = Obj(get_status=lambda t: {'initial_z_offset': initial})
            self.objects['gcode_move'] = Obj(get_status=lambda t: {'homing_origin': [0, 0, final]})

    def test_end_saves_changed_offset(self):
            self.offset(0, 0.03)
            self.obj.requested = False
            self.obj.save_print_offset()
            self.assertEqual(self.log, ['Z_OFFSET_APPLY_PROBE', 'SAVE_CONFIG'])

    def test_unchanged_zero_or_shutdown_does_not_save(self):
            for initial, final in ((0,0), (0.02,0.02), (0,0.0000001), (0.02,0)):
                self.offset(initial, final)
                self.obj.save_print_offset()
                self.assertEqual(self.log, [])
            self.offset(0,0.05)
            self.obj.printer.is_shutdown = lambda: True
            self.obj.save_print_offset()
            self.assertEqual(self.log, [])

    def prime_cmd(self, state):
            return Obj(get=lambda k: state, get_int=lambda *a, **kw: 0,
                       get_float=lambda *a, **kw: 366, error=ValueError)

    def test_inline_cancel_before_prime_skips_E_heat_and_wait(self):
            self.obj.inline_prime(self.prime_cmd('begin'))
            executed = []
            def execute(lines, ack):
                for line in lines:
                    executed.append(line)
                    if line == 'FAST_CANCEL_PRIME STATE=end':
                        self.obj.inline_prime(self.prime_cmd('end'))
            self.obj.process = execute
            self.obj.process_commands(['M83','G92 E0','M104 S250','G1 E3 F60',
                                       'FAST_CANCEL_WAIT P=1000','G1 E-3 F1800',
                                       'FAST_CANCEL_PRIME STATE=end','G1 X361 F700'])
            self.assertEqual(executed, ['FAST_CANCEL_PRIME STATE=end','G1 X361 F700'])
            self.assertEqual(self.log, ['G1 X366.0000 F3000'])
            self.assertTrue(self.obj.prime_skipped)
            self.assertFalse(self.obj.inline_prime_skip)

    def test_inline_cancel_after_prime_begin_preserves_prime(self):
            self.obj.requested = False
            self.obj.inline_prime(self.prime_cmd('begin'))
            self.obj.requested = True
            self.obj.process = lambda lines, ack: list(lines)
            commands = ['M104 S250','G1 E3 F60','FAST_CANCEL_WAIT P=1000']
            self.assertEqual(self.obj.process_commands(commands),commands)
            self.assertFalse(self.obj.stop_wait())
            self.obj.inline_prime(self.prime_cmd('end'))
            self.assertEqual(self.log, [])
            self.assertFalse(self.obj.prime_skipped)

    def test_inline_skipped_prime_allows_emergency_stop(self):
            self.obj.inline_prime(self.prime_cmd('begin'))
            self.obj.process = lambda lines, ack: list(lines)
            self.assertEqual(self.obj.process_commands(['G1 E2','M112']), ['M112'])

    def test_abort_unwinds_nested_macros_without_raising_and_allows_next_request(self):
            executed = []
            def execute(lines, ack):
                for line in lines:
                    executed.append(line)
                    if line == 'DOCK':
                        self.obj.process_commands(['CHECK', 'MARK_DOCKED'])
                    elif line == 'CHECK':
                        self.obj.process_commands(['FAIL', 'CHECK_TAIL'])
                    elif line == 'FAIL':
                        self.obj.dock_abort = True
            self.obj.requested = False
            self.obj.process = execute
            self.obj.process_commands(['DOCK','BASE_RESUME','NEXT_MOVE'])
            self.assertEqual(executed,['DOCK','CHECK','FAIL'])
            self.assertFalse(self.obj.dock_abort)
            self.obj.process_commands(['NEXT_REQUEST'])
            self.assertEqual(executed[-1],'NEXT_REQUEST')

    def test_failed_dock_preserves_original_print_state_and_pauses_once(self):
            self.obj.requested = False
            self.obj.slot = 2
            self.objects['pause_resume'] = Obj(get_status=lambda t: {'is_paused':False})
            saved = {'last_position':[100,120,5,7], 'absolute_extrude':True}
            move = Obj(saved_states={'FAST_CANCEL_CHANGE_TOOL_STATE':saved})
            self.objects['gcode_move'] = move
            self.objects['gcode_macro CHANGE_TOOL_STATE'] = Obj(get_status=lambda t: {'last_x':100,'last_y':120,'last_z':5})
            self.obj.dock_failure(None)
            self.assertEqual(move.saved_states['PAUSE_STATE'],saved)
            self.assertIsNot(move.saved_states['PAUSE_STATE'],saved)
            self.assertEqual(self.log.count('PAUSE'),1)
            self.assertTrue(any('active_tool VALUE=2' in s for s in self.log))
            self.assertTrue(self.obj.dock_abort)
            self.assertEqual(self.log[-1],'FAST_CANCEL_DOCK_FAILED_PAUSED')
            self.assertFalse(self.obj.critical)
            self.log.clear()
            move.saved_states['PAUSE_STATE']={'original':True}
            self.objects['pause_resume'].get_status=lambda t: {'is_paused':True}
            self.obj.dock_failure(None)
            self.assertNotIn('PAUSE',self.log)
            self.assertEqual(move.saved_states['PAUSE_STATE'],{'original':True})

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
                'toolhead': Obj(wait_moves=lambda: None, get_status=lambda t: {'homed_axes': self.homed, 'axis_minimum': [0, 0, 0], 'axis_maximum': [300, 300, 300]}, get_position=lambda: [100, 100, 20]),
                'filament_switch_sensor toolhead_sensor': Obj(get_status=lambda t: {'filament_detected': self.mounted}),
                'gcode_macro TOOL_STATE': Obj(get_status=lambda t: {'active_tool': self.active}),
                'pause_resume': Obj(cmd_CANCEL_PRINT=lambda c: None),
                'gcode_move': Obj(get_status=lambda t: {'homing_origin': [0, 0, 0]}),
            }
            self.obj.printer = Obj(lookup_object=lambda n, default=None: self.objects.get(n, default), is_shutdown=lambda: False)

    def checkpoint(self, phase, tool=0):
            self.obj.checkpoint(Obj(get=lambda key: phase,
                                    get_int=lambda *a, **kw: tool, error=ValueError))

    def test_normal_docking_does_not_drain_motion_queue(self):
            self.obj.requested = False
            self.obj.critical = True
            self.objects['toolhead'].wait_moves = lambda: self.log.append('wait')
            self.checkpoint('docked', 2)
            self.assertEqual(self.log, [])
            self.assertEqual((self.obj.phase, self.obj.slot, self.obj.critical), ('docked', 2, False))

    def test_pending_cancel_or_cleanup_waits_at_docking_boundary(self):
            for requested, cleaning in ((True, False), (False, True)):
                self.obj.requested, self.obj.cleaning = requested, cleaning
                self.log.clear()
                self.objects['toolhead'].wait_moves = lambda: self.log.append('wait')
                self.checkpoint('docked')
                self.assertEqual(self.log, ['wait'])

    def test_parking_boundary_still_waits_without_cancel(self):
            self.obj.requested = False
            self.objects['toolhead'].wait_moves = lambda: self.log.append('wait')
            self.checkpoint('empty')
            self.assertEqual(self.log, ['wait'])

    def test_homing_axis_cleanup_runs_but_following_axis_is_filtered(self):
            self.obj.process = lambda lines, ack: list(lines)
            self.obj.original_home = lambda cmd: self.obj.process_commands(['Probe_Stow'])
            self.assertEqual(self.obj.home_motion(None), ['Probe_Stow'])
            self.assertEqual(self.obj.process_commands(['G28 Y']), [])

    def test_macro_cancel_queues_same_cleanup_once_even_when_paused(self):
            self.obj.requested = False
            self.obj.reactor.register_callback = lambda fn: self.log.append('queued')
            self.obj.cmd_cancel(Obj(error=ValueError))
            self.obj.cmd_cancel(Obj(error=ValueError))
            self.assertEqual(self.log, ['queued'])
            self.assertTrue(self.obj.sd.must_pause_work)

    def test_cancel_during_prime_keeps_waits_and_commands(self):
            self.checkpoint('priming', 1)
            self.assertFalse(self.obj.stop_wait())
            self.obj.process = lambda lines, ack: list(lines)
            self.assertEqual(self.obj.process_commands(['G1 E2', 'FAST_CANCEL_WAIT P=1000']),
                             ['G1 E2', 'FAST_CANCEL_WAIT P=1000'])
            self.checkpoint('docked', 1)
            self.assertTrue(self.obj.stop_wait())
            self.assertEqual(self.obj.process_commands(['NEXT_PRINT_MOVE']), [])

    def test_new_dock_clears_skipped_prime(self):
            self.obj.prime_skipped = True
            self.checkpoint('docking', 2)
            self.assertFalse(self.obj.prime_skipped)

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
