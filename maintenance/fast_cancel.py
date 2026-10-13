"""Cooperative cancellation for the audited LUGOWARE M5P toolchange macros."""
import logging
import copy


class MeshCancelled(Exception):
    pass


class FastCancel:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.reactor = self.printer.get_reactor()
        self.requested = False
        self.cleaning = False
        self.critical = False
        self.phase = 'normal'
        self.slot = -1
        self.message = ''
        self.mesh_active = False
        self.homing_active = False
        self.homing_motion = False
        self.prime_skipped = False
        self.inline_prime_skip = False
        self.command_depth = 0
        self.dock_abort = False
        self.printer.lookup_object('webhooks').register_endpoint('fast_cancel/request', self.request)
        self.gcode.register_command('FAST_CANCEL_PHASE', self.checkpoint)
        self.gcode.register_command('FAST_CANCEL_WAIT', self.dwell)
        self.gcode.register_command('FAST_CANCEL', self.cmd_cancel)
        self.gcode.register_command('FAST_CANCEL_HOME', self.home_checkpoint)
        self.gcode.register_command('FAST_CANCEL_PRIME', self.inline_prime)
        self.gcode.register_command('FAST_CANCEL_DOCK_FAILURE', self.dock_failure)
        self.gcode.register_command('FAST_CANCEL_SAVE_PRINT_OFFSET', self.save_print_offset)
        self.printer.register_event_handler('klippy:ready', self.connect)
        self.printer.register_event_handler('klippy:shutdown', self.shutdown)

    def shutdown(self):
        # Emergency shutdown wins over graceful cancellation. Never schedule
        # recovery travel or leave the command filter blocking a restart.
        self.requested = False
        self.critical = False
        self.inline_prime_skip = False
        self.phase = 'shutdown'
        self.message = 'Emergency shutdown; graceful cancellation abandoned'

    def connect(self):
        self.sd = self.printer.lookup_object('virtual_sdcard')
        self.heaters = self.printer.lookup_object('heaters')
        self.process = self.gcode._process_commands
        self.gcode._process_commands = self.process_commands
        self.old_wait = self.heaters._wait_for_temperature
        self.heaters._wait_for_temperature = self.wait_heater
        self.wait_command = self.gcode.register_command('TEMPERATURE_WAIT', None)
        self.gcode.register_command('TEMPERATURE_WAIT', self.wait_temperature)
        self.dwell_command = self.gcode.ready_gcode_handlers['G4']
        logging.info('Fast cancel: G4 left unchanged (%s); docking uses FAST_CANCEL_WAIT', self.dwell_command)
        self.connect_mesh()
        override = self.printer.lookup_object('homing_override', None)
        if override is not None:
            self.original_home = override.prev_G28
            override.prev_G28 = self.home_motion
            self.original_probe = self.gcode.register_command('PROBE', None)
            self.gcode.register_command('PROBE', self.home_probe)

    def home_probe(self, cmd):
        if not self.homing_active:
            return self.original_probe(cmd)
        self.homing_motion = True
        try:
            return self.original_probe(cmd)
        finally:
            self.homing_motion = False

    def home_checkpoint(self, cmd):
        state = cmd.get('STATE')
        if state not in ('begin', 'end'):
            raise cmd.error('Unknown home checkpoint')
        self.homing_active = state == 'begin'

    def home_motion(self, cmd):
        # Finish the current axis and its probe cleanup, then let the outer
        # homing macro stop before the next axis/movement command.
        self.homing_motion = True
        try:
            return self.original_home(cmd)
        finally:
            self.homing_motion = False

    def connect_mesh(self):
        mesh = self.printer.lookup_object('bed_mesh')
        self.mesh_helper = mesh.bmc.probe_mgr.probe_helper
        self.mesh_probe = self.printer.lookup_object('probe').probe_session
        self.mesh_start = self.mesh_helper.start_probe
        self.mesh_sample = self.mesh_probe._probe
        self.mesh_next = self.mesh_helper._move_next
        self.mesh_finalize = self.mesh_helper._invoke_callback
        self.mesh_helper.start_probe = self.start_mesh
        self.mesh_probe._probe = self.probe_sample
        self.mesh_helper._move_next = self.mesh_move_next
        self.mesh_helper._invoke_callback = self.finalize_mesh

    def check_mesh_cancel(self):
        if self.mesh_active and self.stop_wait() and not self.printer.is_shutdown():
            raise MeshCancelled()

    def probe_sample(self, cmd):
        self.check_mesh_cancel()
        result = self.mesh_sample(cmd)
        # The MCU homing/probe move and probe deactivation have finished.
        self.check_mesh_cancel()
        return result

    def mesh_move_next(self, point):
        self.check_mesh_cancel()
        return self.mesh_next(point)

    def finalize_mesh(self, results):
        self.check_mesh_cancel()
        return self.mesh_finalize(results)

    def start_mesh(self, cmd):
        if not self.printing() or self.cleaning or cmd.get('METHOD', 'automatic').lower() == 'manual':
            return self.mesh_start(cmd)
        self.mesh_active = True
        try:
            self.check_mesh_cancel()
            return self.mesh_start(cmd)
        except MeshCancelled:
            # Keep probe cleanup scripts enabled until the session is closed.
            try:
                if self.mesh_probe.hw_probe_session is not None and not self.printer.is_shutdown():
                    self.mesh_helper._raise_tool()
                    self.printer.lookup_object('toolhead').wait_moves()
            finally:
                if self.mesh_probe.hw_probe_session is not None:
                    self.mesh_probe.end_probe_session()
            logging.info('Fast cancel: bed mesh stopped; partial results discarded')
        finally:
            self.mesh_active = False

    def printing(self):
        return self.printer.lookup_object('print_stats').get_status(self.reactor.monotonic())['state'] in ('printing', 'paused')

    def checkpoint(self, cmd):
        phase = cmd.get('PHASE')
        slot = cmd.get_int('TOOL', -1, minval=-1, maxval=3)
        if phase not in ('normal', 'docking', 'priming', 'prime_skipped', 'docked', 'parking', 'empty'):
            raise cmd.error('Unknown cancellation phase')
        if phase in ('normal', 'docking'):
            self.prime_skipped = False
        elif phase == 'prime_skipped':
            self.prime_skipped = True
        # Keep normal docking continuous with the following print move.
        # A later cancellation still drains queued moves in finish() before
        # inspecting attachment or issuing recovery travel. Keep the parking
        # boundary and pending-cancel/cleanup docking boundaries synchronous.
        if phase == 'empty' or (phase == 'docked' and (self.requested or self.cleaning)):
            self.printer.lookup_object('toolhead').wait_moves()
        self.phase, self.slot = phase, slot
        self.critical = phase in ('docking', 'priming', 'prime_skipped', 'parking')

    def inline_prime(self, cmd):
        state = cmd.get('STATE')
        slot = cmd.get_int('TOOL', minval=0, maxval=3)
        if state == 'begin':
            self.inline_prime_skip = self.requested and not self.cleaning
            self.prime_skipped = self.inline_prime_skip
            self.phase = 'prime_skipped' if self.inline_prime_skip else 'priming'
            self.slot, self.critical = slot, True
        elif state == 'end':
            skipped = self.inline_prime_skip
            self.inline_prime_skip = False
            if skipped:
                # Rejoin the original exit path without extrusion/retraction.
                x = cmd.get_float('EXIT_X')
                self.gcode.run_script_from_command('G1 X%.4f F3000' % x)
        else:
            raise cmd.error('Unknown inline prime checkpoint')

    def dock_failure(self, cmd):
        # Pause without raising a G-code error (which ends virtual SD prints).
        now = self.reactor.monotonic()
        pause = self.printer.lookup_object('pause_resume')
        move = self.printer.lookup_object('gcode_move')
        state = self.printer.lookup_object('gcode_macro CHANGE_TOOL_STATE').get_status(now)
        position = {key: float(state[key]) for key in ('last_x', 'last_y', 'last_z')}
        slot = self.slot
        already_paused = pause.get_status(now)['is_paused']
        # CHANGE_TOOL saved this before changing modes or priming. On a retry,
        # retain the original PAUSE_STATE instead of capturing the dock position.
        saved = copy.deepcopy(move.saved_states.get('FAST_CANCEL_CHANGE_TOOL_STATE'))
        if not already_paused:
            self.gcode.run_script_from_command('PAUSE')
            if saved is not None:
                move.saved_states['PAUSE_STATE'] = saved
            for key, value in position.items():
                self.gcode.run_script_from_command(
                    'SET_GCODE_VARIABLE MACRO=CHANGE_TOOL_STATE VARIABLE=%s VALUE=%.9f'
                    % (key, value))
        if slot in range(4):
            self.gcode.run_script_from_command(
                'SET_GCODE_VARIABLE MACRO=TOOL_STATE VARIABLE=active_tool VALUE=%d\n'
                'SET_GCODE_VARIABLE MACRO=TOOL_STATE VARIABLE=is_parked VALUE=1' % slot)
        self.phase, self.critical = 'empty', False
        self.inline_prime_skip = False
        self.dock_abort = True
        self.message = 'Tool attachment failed; print paused'
        self.gcode.respond_info('FAST_CANCEL_DOCK_FAILED_PAUSED')

    def process_commands(self, commands, need_ack=True):
        def filtered():
            for line in commands:
                command = line.split(';', 1)[0].strip().upper().split()
                recovery = command and command[0] in ('M112', 'RESTART', 'FIRMWARE_RESTART')
                if getattr(self, 'dock_abort', False) and not recovery:
                    break
                if (getattr(self, 'inline_prime_skip', False) and not recovery
                        and not self.printer.is_shutdown()
                        and (not command or command[0] != 'FAST_CANCEL_PRIME')):
                    continue
                if (self.requested and not self.cleaning and not self.critical
                        and not getattr(self, 'mesh_active', False)
                        and not getattr(self, 'homing_motion', False)
                        and not recovery and not self.printer.is_shutdown()):
                    break
                yield line
        self.command_depth = getattr(self, 'command_depth', 0) + 1
        try:
            return self.process(filtered(), need_ack)
        finally:
            self.command_depth -= 1
            if self.command_depth == 0:
                self.dock_abort = False

    def stop_wait(self):
        # Once priming has begun, preserve all of its heat/time waits.
        return self.requested and not self.cleaning and self.phase != 'priming'

    def dwell(self, cmd):
        if not self.printing() or self.cleaning:
            return self.dwell_command(cmd)
        duration = cmd.get_float('P', 0., minval=0.) / 1000.
        toolhead = self.printer.lookup_object('toolhead')
        if self.stop_wait() or self.printer.is_shutdown():
            return
        toolhead.wait_moves()
        deadline = self.reactor.monotonic() + duration
        now = self.reactor.monotonic()
        while now < deadline and not self.stop_wait() and not self.printer.is_shutdown():
            now = self.reactor.pause(min(now + 0.1, deadline))

    def wait_heater(self, heater):
        if self.printer.get_start_args().get('debugoutput') is not None:
            return
        when = self.reactor.monotonic()
        while not self.printer.is_shutdown() and heater.check_busy(when):
            if self.stop_wait():
                return
            self.printer.lookup_object('toolhead').get_last_move_time()
            when = self.reactor.pause(when + 0.1)

    def wait_temperature(self, cmd):
        if not self.printing() or self.cleaning:
            return self.wait_command(cmd)
        if self.printer.get_start_args().get('debugoutput') is not None:
            return
        name = cmd.get('SENSOR')
        low = cmd.get_float('MINIMUM', float('-inf'))
        high = cmd.get_float('MAXIMUM', float('inf'), above=low)
        if low == float('-inf') and high == float('inf'):
            raise cmd.error('TEMPERATURE_WAIT requires MINIMUM or MAXIMUM')
        sensor = self.heaters.heaters.get(name) or self.printer.lookup_object(name)
        temperatures = self.printer.lookup_object('lugo_tool_temperature', None)
        when = self.reactor.monotonic()
        while not self.printer.is_shutdown() and not self.stop_wait():
            shift = 0
            if name == 'heater_bed' and temperatures:
                shift = temperatures.wait_shift(name)
            if name == 'extruder' and temperatures and temperatures.start_tool is not None and not temperatures.changing:
                tool = temperatures.start_tool
                base, override = temperatures.base[tool], temperatures.overrides[tool]
                if base is not None and override is not None:
                    shift = override - base
            value, target = sensor.get_temp(when)
            if low + shift <= value <= high + shift:
                return
            self.printer.lookup_object('toolhead').get_last_move_time()
            when = self.reactor.pause(when + 0.1)

    def request(self, request):
        if self.printer.is_shutdown():
            raise request.error('Printer is shutdown')
        if self.requested:
            request.send({'accepted': True, 'phase': self.phase})
            return
        if not self.printing():
            raise request.error('No active print to cancel')
        self.queue_cancel()
        request.send({'accepted': True, 'phase': self.phase})

    def cmd_cancel(self, cmd):
        if self.printer.is_shutdown():
            raise cmd.error('Printer is shutdown')
        if self.requested:
            return
        self.queue_cancel()

    def queue_cancel(self):
        logging.info('Fast cancel requested: phase=%s slot=%s critical=%s',
                     self.phase, self.slot, self.critical)
        self.requested = True
        self.message = 'Cancelling at the next mechanical safe point'
        self.sd.must_pause_work = True
        self.reactor.register_callback(self.finish)

    def save_print_offset(self, cmd=None):
        # Called only after end/cancel cleanup. SAVE_CONFIG restarts Klipper.
        if self.printer.is_shutdown():
            return
        tracker = self.printer.lookup_object('gcode_macro Z_OFFSET_TRACKER', None)
        if tracker is None:
            return
        now = self.reactor.monotonic()
        initial = float(tracker.get_status(now)['initial_z_offset'])
        offset = float(self.printer.lookup_object('gcode_move').get_status(now)['homing_origin'][2])
        if abs(offset - initial) < 0.000001 or abs(offset) < 0.000001:
            return
        self.printer.lookup_object('toolhead').wait_moves()
        if self.printer.is_shutdown():
            return
        logging.info('Saving print Z offset: initial=%s final=%s', initial, offset)
        self.gcode.run_script_from_command('Z_OFFSET_APPLY_PROBE')
        self.gcode.run_script_from_command('SAVE_CONFIG')

    def finish(self, eventtime):
        # Wait for the executing macro stack to unwind before recovery moves.
        with self.gcode.get_mutex():
            if not self.requested or self.printer.is_shutdown():
                return
            while self.sd.work_timer is not None:
                if not self.requested or self.printer.is_shutdown():
                    return
                self.reactor.pause(self.reactor.monotonic() + .01)
            self.cleaning = True
            cleanup_complete = False
            try:
                if self.printer.is_shutdown():
                    return
                toolhead = self.printer.lookup_object('toolhead')
                toolhead.wait_moves()
                status = toolhead.get_status(self.reactor.monotonic())
                if getattr(self, 'homing_active', False):
                    # homing_override sets a provisional Z=0 before probing;
                    # it must not be treated as a physically homed position.
                    toolhead.get_kinematics().clear_homing_state('xyz')
                    self.homing_active = False
                    raise self.gcode.error('Homing cancelled; position not established, return skipped.')
                mounted = self.printer.lookup_object('filament_switch_sensor toolhead_sensor').get_status(self.reactor.monotonic())['filament_detected']
                state = self.printer.lookup_object('gcode_macro TOOL_STATE').get_status(self.reactor.monotonic())
                tool = self.slot if self.phase == 'docked' else int(state['active_tool'])
                if self.critical or (mounted and (self.phase == 'empty' or tool not in range(4))):
                    raise self.gcode.error('Tool attachment is uncertain; automatic parking skipped. Inspect the head.')
                if set('xyz') - set(status['homed_axes']):
                    raise self.gcode.error('Axes are not homed; automatic parking and return skipped.')
                # All parking and return motion is maintained in printer_base.cfg.
                self.gcode.run_script_from_command(
                    '_FAST_CANCEL_MOTION TOOL=%d SKIP_EXTRUDE=%d'
                    % (tool, int(getattr(self, 'prime_skipped', False))))
                self.message = 'Print cancelled'
                cleanup_complete = True
            except Exception as exc:
                logging.exception('Fast cancel parking failed')
                self.message = str(exc)
                self.gcode.respond_info('Cancellation: ' + self.message)
            finally:
                try:
                    self.gcode.run_script_from_command('_FAST_CANCEL_FINALIZE')
                except Exception:
                    logging.exception('CFG cancel finalization failed; applying heater fallback')
                finally:
                    # Safety fallback even if a user-edited CFG macro fails.
                    self.heaters.turn_off_all_heaters()
                temperatures = self.printer.lookup_object('lugo_tool_temperature', None)
                if temperatures:
                    temperatures.reset()
                # Finalize cancellation before SAVE_CONFIG can restart Klipper.
                try:
                    self.printer.lookup_object('pause_resume').cmd_CANCEL_PRINT(
                        self.gcode.create_gcode_command('CANCEL_PRINT', '', {}))
                    self.sd.do_cancel()
                finally:
                    self.requested = self.cleaning = self.critical = False
                    self.phase, self.slot = 'normal', -1
                    self.inline_prime_skip = False
            if cleanup_complete:
                try:
                    self.save_print_offset()
                except Exception as exc:
                    logging.exception('Print Z offset auto-save failed')
                    self.gcode.respond_info('Z offset auto-save failed: ' + str(exc))

    def get_status(self, eventtime):
        return {'cleaning': self.cleaning, 'requested': self.requested, 'phase': self.phase, 'tool': self.slot, 'message': self.message}


def load_config(config):
    return FastCancel(config)
