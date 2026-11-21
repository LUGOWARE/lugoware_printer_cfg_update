"""Operator-confirmed recovery from an interrupted, preheat dock check."""
import logging
import re


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

    def begin_hold(self, slot):
        now = self.reactor.monotonic()
        position = tuple(self.printer.lookup_object('toolhead').get_status(now)['position'][:3])
        route = self.printer.lookup_object('gcode_macro _T%d_RETRY_DOCK_XY' % (slot + 1), None)
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
                self.record['id'] = self.sequence
            return
        dock = self.candidate
        self.record = None
        sd = self.fast.sd
        if (dock is None or dock[1] != slot or self.fast.command_depth != dock[0] + 1
                or not sd.is_cmd_from_sd() or sd.current_file is None):
            return
        self.record = {'dock': dock[2], 'depth': dock[0], 'slot': slot, 'id': self.sequence,
                       'file': sd.current_file, 'offset': sd.get_file_position(),
                       'position': position, 'route': settings, 'continuation': [], 'sealed': False}

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

    def require_safe(self, gcmd, record, at_dock):
        fast = self.fast
        if (self.printer.is_shutdown() or fast.requested or fast.cleaning
                or fast.phase != 'dock_sensor_hold'
                or not self.printer.lookup_object('pause_resume').is_paused
                or fast.sd.current_file is not record['file']
                or fast.sd.file_position != record['offset'] or fast.sd.is_active()):
            raise gcmd.error('Held print changed. Dock recovery stopped.')
        now = self.reactor.monotonic()
        source = self.printer.lookup_object('toolhead_auxiliary')
        if source.get_status(now)['state'] != 'disconnected':
            raise gcmd.error('Confirm the carriage is empty and the tool is seated in its rack.')
        for heater in self.heaters():
            if heater.target_temp or heater.last_pwm_value:
                raise gcmd.error('Wait for both heater outputs to turn off before dock recovery.')
        head = self.printer.lookup_object('toolhead').get_status(now)
        move = self.printer.lookup_object('gcode_move').get_status(now)
        if (set(head['homed_axes']) != set('xyz') or not move['absolute_coordinates']
                or any(abs(head['position'][i] - move['gcode_position'][i]) > .1 for i in (0, 1))
                or abs(head['position'][2] - record['position'][2]) > .1):
            raise gcmd.error('Homing or position changed. Dock recovery stopped.')
        if at_dock:
            x, y = record['route']['retry_x'], record['route']['retry_y']
            if (abs(head['position'][0] - x) > .1 or abs(head['position'][1] - y) > .1
                    or any(abs(a - b) > .1 for a, b in zip(head['position'], record['position']))):
                raise gcmd.error('Carriage is outside the verified dock exit. Cancel the held print.')

    def resume(self, gcmd):
        if not self.available() or gcmd.get_int('CONFIRMED', 0) != self.record['id']:
            raise gcmd.error('No recoverable dock pause. Confirm the tool is parked before retrying.')
        record = self.record
        self.require_safe(gcmd, record, at_dock=True)
        fast = self.fast
        run = self.gcode.run_script_from_command
        temps = self.printer.lookup_object('lugo_tool_temperature')
        self.recovering = True
        temps.depth += 1
        temps.changing += 1
        try:
            run('SAVE_GCODE_STATE NAME=LUGO_DOCK_RECOVERY')
            _, release_x, clear_x = record['route']['retry_exit']
            for command in ('G1 X%g F700' % release_x, 'G1 X%g F1800' % clear_x,
                            'G1 X0 F3600', 'G28 X Y'):
                self.require_safe(gcmd, record, at_dock=False)
                run(command + '\nM400')
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
