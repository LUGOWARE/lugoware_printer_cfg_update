"""Operator-confirmed recovery from an interrupted, preheat dock check."""
import logging
import re
from copy import deepcopy


DOCK = re.compile(r'^DOCK_TOOL_([0-3])(?:\s|$)', re.I)
FILE_COMMANDS = {'START_PRINT', 'CHANGE_TOOL'}


class DockRecovery:
    def __init__(self, fast):
        self.fast = fast
        self.printer = fast.printer
        self.gcode = fast.gcode
        self.reactor = fast.reactor
        self.outer_command = None
        self.candidate = None
        self.record = None
        self.recovering = False
        self.sequence = 0
        self.gcode.register_command('TOOLHEAD_RESUME_DOCK', self.resume)

    def before_line(self, line, command, depth):
        if depth == 1:
            self.outer_command = command if command in FILE_COMMANDS and self.fast.sd.is_cmd_from_sd() else None
            if self.outer_command:
                self.record = None
        if not self.outer_command:
            return
        dock = DOCK.match(line.strip())
        if dock and self.fast.sd.current_file is not None:
            self.candidate = (depth, int(dock[1]), line)

    def begin_hold(self, slot, returned=False):
        now = self.reactor.monotonic()
        position = tuple(self.printer.lookup_object('toolhead').get_status(now)['position'][:3])
        move = self.printer.lookup_object('gcode_move').get_status(now)
        recovery_z = (move['position'][2], move['gcode_position'][2])
        route = self.printer.lookup_object('gcode_macro _TOOL_RETRY_DOCK_XY_T%d' % (slot + 1), None)
        settings = route.get_status(now) if route is not None else {}
        loaded = self.printer.lookup_object('configfile').get_status(now)['settings']
        if (not {'retry_x', 'retry_y', 'retry_exit'} <= settings.keys()
                or loaded.get('homing_override', {}).get('axes') != 'z'
                or not loaded['stepper_x']['position_min'] <= 0 <= loaded['stepper_x']['position_max']):
            self.record = None
            return
        self.sequence += 1
        if self.recovering:
            if self.record is not None:
                self.record['position'] = position
                self.record['recovery_z'] = recovery_z
                self.record['id'] = self.sequence
                self.record['returned'] = returned
            return
        dock = self.candidate
        self.record = None
        sd = self.fast.sd
        if (dock is None or dock[1] != slot or self.fast.command_depth != dock[0] + 1
                or not sd.is_cmd_from_sd() or sd.current_file is None):
            return
        self.record = {'dock': dock[2], 'depth': dock[0], 'slot': slot, 'id': self.sequence,
                       'file': sd.current_file, 'offset': sd.get_file_position(),
                       'position': position, 'recovery_z': recovery_z, 'route': settings, 'returned': returned,
                       'continuation': [], 'sealed': False}

    def begin_print_hold(self, slot, targets):
        sd = self.fast.sd
        pause = self.printer.lookup_object('pause_resume')
        now = self.reactor.monotonic()
        head = self.printer.lookup_object('toolhead').get_status(now)
        mover = self.printer.lookup_object('gcode_move')
        move = mover.get_status(now)
        settings = self.printer.lookup_object('configfile').get_status(now)['settings']
        state = mover.saved_states.get('PAUSE_STATE')
        if (not state or not pause.is_paused or not pause.sd_paused
                or sd.current_file is None or sd.is_active() or sd.is_cmd_from_sd()
                or slot not in range(4) or min(targets) <= 0.
                or not move['absolute_coordinates'] or set(head['homed_axes']) != set('xyz')
                or max(head['position'][2], move['position'][2]) + 5. > head['axis_maximum'][2]
                or any(abs(head['position'][i] - move['gcode_position'][i]) > .1 for i in (0, 1))
                or settings.get('homing_override', {}).get('axes') != 'z'
                or 'gcode_macro resume_action_t%d' % slot not in settings):
            return
        self.sequence += 1
        self.record = {'kind': 'print', 'id': self.sequence, 'slot': slot,
                       'file': sd.current_file, 'offset': sd.file_position, 'sealed': True,
                       'position': tuple(head['position'][:3]), 'xyz': tuple(move['gcode_position'][:3]),
                       'targets': targets, 'pause_state': deepcopy(state)}
        logging.info('Toolhead print recovery saved: slot=%s offset=%s xyz=%s',
                     slot, sd.file_position, self.record['xyz'])

    def capture_tail(self, depth, line, lines):
        record = self.record
        if not self.recovering and record and not record['sealed'] and depth <= record['depth']:
            record['continuation'].append('\n'.join([line, *lines]))

    def end_frame(self):
        record = self.record
        if record and not record['sealed']:
            if self.fast.phase == 'dock_sensor_hold' and self.fast.dock_abort:
                record['sealed'] = True
            else:
                self.record = None
        self.candidate = None
        self.outer_command = None

    def available(self):
        record = self.record
        if not record:
            return False
        sd = self.fast.sd
        return bool(record and record['sealed'] and not self.recovering
                    and self.fast.phase == 'dock_sensor_hold'
                    and self.fast.slot == record['slot']
                    and sd.current_file is record['file']
                    and sd.file_position == record['offset'] and not sd.is_active())

    def heaters(self):
        return (self.printer.lookup_object('extruder').get_heater(),
                self.printer.lookup_object('heater_generic Toolhead'))

    def require_hold(self, gcmd, record):
        fast = self.fast
        if (self.printer.is_shutdown() or fast.requested or fast.cleaning
                or not self.printer.lookup_object('pause_resume').is_paused
                or fast.sd.current_file is not record['file']
                or fast.sd.file_position != record['offset'] or fast.sd.is_active()):
            raise gcmd.error('Held print changed. Dock recovery stopped.')

    def require_empty(self, gcmd, record):
        self.require_hold(gcmd, record)
        if self.fast.phase != 'dock_sensor_hold':
            raise gcmd.error('Dock recovery is no longer waiting for tool confirmation.')
        now = self.reactor.monotonic()
        source = self.printer.lookup_object('toolhead_auxiliary')
        if source.get_status(now)['state'] != 'disconnected':
            raise gcmd.error('Confirm the carriage is empty and the tool is seated in its rack.')
        for heater in self.heaters():
            if heater.target_temp or heater.last_pwm_value:
                raise gcmd.error('Wait for both heater outputs to turn off before dock recovery.')

    def require_safe(self, gcmd, record, at_dock):
        self.require_empty(gcmd, record)
        now = self.reactor.monotonic()
        head = self.printer.lookup_object('toolhead').get_status(now)
        mover = self.printer.lookup_object('gcode_move')
        move = mover.get_status(now)
        # Bed mesh can change physical Z during an XY move at constant G-code Z.
        # Verify the actual position through the active transform as well.
        actual_z = mover.position_with_transform()[2]
        expected_z, expected_gcode_z = record['recovery_z']
        if (set(head['homed_axes']) != set('xyz') or not move['absolute_coordinates']
                or any(abs(head['position'][i] - move['gcode_position'][i]) > .1 for i in (0, 1))
                or abs(actual_z - expected_z) > .1
                or abs(move['position'][2] - expected_z) > .1
                or abs(move['gcode_position'][2] - expected_gcode_z) > .1):
            logging.warning('Dock recovery pose check failed: axes=%s head=%s gcode=%s '
                            'untransformed_z=%s expected_z=%s expected_gcode_z=%s',
                            head['homed_axes'], head['position'][:3], move['gcode_position'][:3],
                            actual_z, expected_z, expected_gcode_z)
            raise gcmd.error('Homing or position changed. Dock recovery stopped.')
        if not at_dock:
            return False
        x, y = record['route']['retry_x'], record['route']['retry_y']
        saved_x, saved_y, _ = record['position']
        if record.get('returned'):
            if (abs(saved_x - 10.) <= .1 and abs(saved_y - 125.) <= .1
                    and all(abs(a - b) <= .1 for a, b in zip(head['position'], record['position']))):
                return True
            raise gcmd.error('Carriage position changed from the verified X10 Y125 wait position.')
        if abs(saved_x - x) > .1 or abs(saved_y - y) > .1:
            raise gcmd.error('The saved tool position is outside the verified dock exit.')
        current_x, current_y = head['position'][:2]
        if abs(current_x) <= .1 and abs(current_y - saved_y) <= .1:
            # The empty carriage is already clear of the rack, e.g. after G28 X.
            return True
        if any(abs(a - b) > .1 for a, b in zip(head['position'], record['position'])):
            raise gcmd.error('Carriage position changed outside the verified dock or its X0 exit. Print remains paused.')
        return False

    def home_xy(self):
        # Only these two periodic jobs can wait. Keep the sensor watchdog,
        # status publishing and all motion, cancel and heater callbacks live.
        deferred = {
            ('exclude_tool_guard', 'ExcludeToolGuard.flush_pending'),
            ('lugo_recovery', 'Recovery.tick'),
        }
        monitored = deferred | {
            ('paused_tool_service', 'PausedToolService.watchdog'),
            ('webhooks', 'QueryStatusHelper._do_query'),
        }
        samples = {}
        wrapped = []
        active = True

        def profile(callback, key):
            name = key[1]
            row = samples[name] = dict(calls=0, deferred=0, max_ms=0., max_dispatch_ms=0.)

            def measured(eventtime):
                if not active:
                    return callback(eventtime)
                start = self.reactor.monotonic()
                row['max_dispatch_ms'] = max(row['max_dispatch_ms'], (start - eventtime) * 1000.)
                if key in deferred:
                    row['deferred'] += 1
                    return start + .25
                row['calls'] += 1
                try:
                    return callback(eventtime)
                finally:
                    row['max_ms'] = max(row['max_ms'], (self.reactor.monotonic() - start) * 1000.)

            return measured

        try:
            for timer in getattr(self.reactor, '_timers', ()):
                callback = timer.callback
                module = getattr(callback, '__module__', None)
                name = getattr(callback, '__qualname__', None)
                if not isinstance(module, str) or not isinstance(name, str):
                    continue
                key = (module.rsplit('.', 1)[-1], name)
                if key in monitored:
                    wrapper = profile(callback, key)
                    timer.callback = wrapper
                    wrapped.append((timer, callback, wrapper))
            self.gcode.run_script_from_command('G28 X Y\nM400')
        finally:
            active = False
            for timer, callback, wrapper in wrapped:
                if timer.callback is wrapper:
                    timer.callback = callback
            if samples:
                logging.info('Dock recovery XY homing callback timing: %s', samples)

    def resume(self, gcmd):
        if not self.available() or gcmd.get_int('CONFIRMED', 0) != self.record['id']:
            raise gcmd.error('No recoverable dock pause. Confirm the tool is parked before retrying.')
        record = self.record
        if record.get('kind') == 'print':
            return self.resume_print(gcmd, record)
        already_clear = self.require_safe(gcmd, record, at_dock=True)
        fast = self.fast
        run = self.gcode.run_script_from_command
        temps = self.printer.lookup_object('lugo_tool_temperature')
        self.recovering = True
        temps.depth += 1
        temps.changing += 1
        try:
            run('SAVE_GCODE_STATE NAME=LUGO_DOCK_RECOVERY')
            _, release_x, clear_x = record['route']['retry_exit']
            retreat = () if already_clear else ('G1 X%g F700' % release_x, 'G1 X%g F1800' % clear_x,
                                               'G1 X0 F3600')
            for command in retreat:
                self.require_safe(gcmd, record, at_dock=False)
                run(command + '\nM400')
            self.require_safe(gcmd, record, at_dock=False)
            self.home_xy()
            self.require_safe(gcmd, record, at_dock=False)
            run('RESTORE_GCODE_STATE NAME=LUGO_DOCK_RECOVERY MOVE=0')
            run(record['dock'])
            if fast.dock_abort or fast.requested or self.printer.is_shutdown():
                return
            if fast.phase != 'docked' or fast.slot != record['slot']:
                raise gcmd.error('The tool did not finish docking.')
            for script in record['continuation']:
                run(script)
                if fast.dock_abort or fast.requested or self.printer.is_shutdown():
                    return
            run('M400')
            if fast.requested or self.printer.is_shutdown():
                return
            # Resume the SD file after the interrupted command without moving
            # back to the original pause point, which is inside the dock.
            run('SAVE_GCODE_STATE NAME=PAUSE_STATE\nBASE_RESUME')
        except Exception:
            self.record = None
            if not self.printer.is_shutdown():
                fast.phase = 'dock_sensor_hold'
                fast.critical = True
                fast.message = 'Dock recovery did not finish. Inspect the tool and cancel.'
                for heater in self.heaters():
                    heater.set_temp(0.)
            logging.exception('Dock recovery did not finish')
            raise
        else:
            if fast.phase != 'dock_sensor_hold' and not fast.dock_abort:
                self.record = None
        finally:
            temps.depth -= 1
            temps.changing -= 1
            self.recovering = False

    def check_print_pose(self, gcmd, xyz=None, physical=None):
        now = self.reactor.monotonic()
        head = self.printer.lookup_object('toolhead').get_status(now)
        mover = self.printer.lookup_object('gcode_move')
        move = mover.get_status(now)
        if (set(head['homed_axes']) != set('xyz') or not move['absolute_coordinates']
                or any(abs(head['position'][i] - move['gcode_position'][i]) > .1 for i in (0, 1))
                or abs(mover.position_with_transform()[2] - move['position'][2]) > .1
                or (xyz is not None and any(abs(a - b) > .1 for a, b in
                                            zip(xyz, move['gcode_position'])))
                or (physical is not None and any(abs(a - b) > .1 for a, b in
                                                 zip(physical, head['position'])))):
            raise gcmd.error('Homing or position changed. Print recovery stopped.')

    def require_redocked(self, gcmd, record):
        self.require_hold(gcmd, record)
        now = self.reactor.monotonic()
        source = self.printer.lookup_object('toolhead_auxiliary')
        tool = self.printer.lookup_object('gcode_macro TOOL_STATE').get_status(now)
        if (self.fast.dock_abort or self.fast.phase != 'docked' or self.fast.slot != record['slot']
                or tool['active_tool'] != record['slot'] or tool['is_parked']
                or source.get_status(now)['state'] != 'connected'):
            raise gcmd.error('The tool did not finish docking. Print recovery stopped.')
        return tool

    def resume_print(self, gcmd, record):
        self.require_empty(gcmd, record)
        self.check_print_pose(gcmd, record['xyz'], record['position'])
        run = self.gcode.run_script_from_command
        temps = self.printer.lookup_object('lugo_tool_temperature')
        mover = self.printer.lookup_object('gcode_move')
        nozzle, auxiliary = self.heaters()
        nozzle_target, auxiliary_target = record['targets']
        x, y, z = record['xyz']
        safe_z = z + 5.
        self.recovering = True
        temps.depth += 1
        temps.changing += 1
        try:
            run('G1 Z%.9f F1000\nM400' % safe_z)
            self.require_empty(gcmd, record)
            self.check_print_pose(gcmd, (x, y, safe_z))
            self.home_xy()
            self.require_empty(gcmd, record)
            self.check_print_pose(gcmd)
            now = self.reactor.monotonic()
            if abs(mover.get_status(now)['gcode_position'][2] - safe_z) > .1:
                raise gcmd.error('Safe Z height changed during XY homing.')
            nozzle.set_temp(nozzle_target)
            self.wait_print_temperature(gcmd, record, ((nozzle, nozzle_target),), docked=False)
            run('RESUME_ACTION_T%d TEMP=%d PRIME=0\nM400'
                % (record['slot'], round(auxiliary_target)))
            tool = self.require_redocked(gcmd, record)
            nozzle.set_temp(nozzle_target)
            auxiliary.set_temp(auxiliary_target)
            self.wait_print_temperature(gcmd, record, ((nozzle, nozzle_target),
                                                        (auxiliary, auxiliary_target)), docked=True)
            self.require_redocked(gcmd, record)
            run('G90\nG1 X%.9f Y%.9f F6000\nM400' % (x, y))
            self.require_redocked(gcmd, record)
            self.check_print_pose(gcmd, (x, y, safe_z))
            run('G1 Z%.9f F1000\nM400' % z)
            self.require_redocked(gcmd, record)
            self.check_print_pose(gcmd, record['xyz'], record['position'])
            speed = tool['tc_deretract_speed'] or tool['toolchange_retract_speed']
            length = tool['toolchange_retract'] + tool['tc_deretract_extra']
            run('M83\nG1 E%.9f F%.9f\nM400' % (length, speed * 60.))
            self.require_redocked(gcmd, record)
            mover.saved_states['PAUSE_STATE'] = record['pause_state']
            run('PRINT_SENSOR_GATE ENABLE=1\nBASE_RESUME')
            self.record = None
        except Exception:
            self.record = None
            if not self.printer.is_shutdown():
                nozzle.set_temp(0.)
                auxiliary.set_temp(0.)
                self.fast.phase = 'dock_sensor_hold'
                self.fast.critical = True
            logging.exception('Toolhead print recovery stopped')
            raise
        finally:
            temps.depth -= 1
            temps.changing -= 1
            self.recovering = False

    def require_empty_carriage_for_dock(self, gcmd, record):
        self.require_hold(gcmd, record)
        source = self.printer.lookup_object('toolhead_auxiliary')
        if (self.fast.phase != 'dock_sensor_hold'
                or self.fast.dock_abort
                or source.get_status(self.reactor.monotonic())['state'] != 'disconnected'
                or self.heaters()[1].target_temp or self.heaters()[1].last_pwm_value):
            raise gcmd.error('Empty carriage or auxiliary heater state changed before docking.')

    def wait_print_temperature(self, gcmd, record, heaters, docked):
        deadline = self.reactor.monotonic() + 120.
        while True:
            if docked:
                self.require_redocked(gcmd, record)
            else:
                self.require_empty_carriage_for_dock(gcmd, record)
            now = self.reactor.monotonic()
            values = [(heater.get_temp(now), target) for heater, target in heaters]
            if any(abs(active - target) > .01 for (_, active), target in values):
                raise gcmd.error('A heater target changed during print recovery.')
            if all(abs(temp - target) <= 2. for (temp, _), target in values):
                return
            if now >= deadline:
                raise gcmd.error('Print recovery heating timed out.')
            self.reactor.pause(min(deadline, now + .2))
