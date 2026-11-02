"""Defer tool changes for excluded objects; keep machine macros outside exclusion."""
import logging
import re
import shlex

NAME = re.compile(r'\bNAME=([^\s;]+)', re.I)

class ExcludeToolGuard:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.depth = 0
        self.reset()
        self.printer.register_event_handler('klippy:ready', self.ready)
        self.printer.register_event_handler('virtual_sdcard:reset_file', self.reset)

    def reset(self):
        self.pending = None
        self.pending_temp = None
        self.upcoming = None
        self.skipped = 0
        self.replayed = 0
        self.filtered_wipe_gaps = 0

    def ready(self):
        self.sd = self.printer.lookup_object('virtual_sdcard')
        self.exclude = self.printer.lookup_object('exclude_object')
        self.original = {}
        handlers = {'CHANGE_TOOL': self.change_tool,
                    'EXCLUDE_OBJECT_START': self.start_object,
                    'EXCLUDE_OBJECT_END': self.end_object,
                    'M104': self.temperature, 'M109': self.temperature}
        for name, handler in handlers.items():
            old = self.gcode.register_command(name, None)
            if old is None:
                raise self.printer.config_error('exclude_tool_guard requires ' + name)
            self.original[name] = old
            self.gcode.register_command(name, handler)
        # Cancellation/parking must remain real movement even if an object is excluded.
        for name in ('PARK_CURRENT', 'DOCK_TOOL_0', 'DOCK_TOOL_1', 'DOCK_TOOL_2',
                     'DOCK_TOOL_3', '_FAST_CANCEL_RETURN', 'CANCEL_PRINT', 'END_PRINT'):
            old = self.gcode.register_command(name, None)
            if old is not None:
                self.gcode.register_command(name, lambda cmd, fn=old: self.physical(fn, cmd))

    def get_status(self, eventtime):
        return {'skipped_toolchanges': self.skipped, 'deferred_toolchange': self.pending is not None,
                'replayed_toolchanges': self.replayed, 'upcoming_object': self.upcoming,
                'filtered_wipe_gaps': self.filtered_wipe_gaps}

    def upcoming_object(self):
        # Read a separate handle, never disturb the virtual-SD buffered reader.
        path = self.sd.file_path()
        if not path:
            return None
        with open(path, 'rb') as stream:
            stream.seek(self.sd.get_file_position())
            data = stream.read(262144)
        for raw in data.decode('utf-8', errors='replace').splitlines():
            line = raw.split(';', 1)[0].strip()
            if not line:
                continue
            command = line.split()[0].upper()
            if command == 'EXCLUDE_OBJECT_START':
                match = NAME.search(line)
                return match.group(1).upper() if match else None
            if command in ('CHANGE_TOOL', 'END_PRINT', 'PRINT_END', 'START_PRINT'):
                return None
        return None

    def is_excluded_wipe_gap(self, name):
        path = self.sd.file_path()
        if not path:
            return False
        # Only a bounded, explicit wipe between END and START of the SAME object.
        with open(path, 'rb') as stream:
            stream.seek(self.sd.get_file_position())
            data = stream.read(8192)
        in_wipe = saw_wipe = ended_wipe = False
        for raw in data.decode('utf-8', errors='replace').splitlines():
            text = raw.strip()
            if text == ';WIPE_START':
                in_wipe = saw_wipe = True
                continue
            if text == ';WIPE_END':
                in_wipe = False
                ended_wipe = True
                continue
            line = text.split(';', 1)[0].strip()
            if not line:
                continue
            command = line.split()[0].upper()
            if command == 'EXCLUDE_OBJECT_START':
                match = NAME.search(line)
                return bool(saw_wipe and ended_wipe and not in_wipe and match
                            and match.group(1).upper() == name)
            if command in ('SET_VELOCITY_LIMIT', 'M204', 'M140'):
                continue
            # Slicer may retract E before the WIPE_START comment. Permit only
            # an explicit non-positive E move without XYZ outside the wipe.
            if command in ('G0', 'G1') and not in_wipe and not saw_wipe:
                tokens = line.upper().split()[1:]
                if tokens and all(token[0] in ('E', 'F') for token in tokens):
                    extrusion = re.search(r'(?:^|\s)E([-+0-9.eE]+)', line)
                    if extrusion and float(extrusion.group(1)) <= 0:
                        continue
                return False
            if command in ('G0', 'G1') and in_wipe:
                extrusion = re.search(r'(?:^|\s)E([-+0-9.eE]+)', line)
                if extrusion and float(extrusion.group(1)) > 0:
                    return False
                continue
            return False
        return False

    def end_object(self, gcmd):
        # Unnamed END is also used by our physical-machine-macro protection.
        name = gcmd.get('NAME', None)
        if (not self.depth and name and self.sd.is_cmd_from_sd()
                and name.upper() == self.exclude.current_object
                and name.upper() in self.exclude.excluded_objects
                and self.is_excluded_wipe_gap(name.upper())):
            self.filtered_wipe_gaps += 1
            logging.info('Exclude tool guard: keeping excluded wipe gap for %s at byte %d',
                         name.upper(), self.sd.get_file_position())
            return
        return self.original['EXCLUDE_OBJECT_END'](gcmd)

    def physical(self, callback, gcmd):
        if self.depth:
            return callback(gcmd)
        previous = self.exclude.current_object
        path = self.sd.file_path()
        if previous is not None:
            self.gcode.run_script_from_command('EXCLUDE_OBJECT_END')
        self.depth += 1
        try:
            result = callback(gcmd)
        finally:
            self.depth -= 1
        # Only restore the object after successful completion, never after cancellation/reset.
        if previous is not None and self.sd.file_path() == path and path:
            line = 'EXCLUDE_OBJECT_START NAME=' + shlex.quote(previous)
            cmd = self.gcode.create_gcode_command('EXCLUDE_OBJECT_START', line, {'NAME': previous})
            self.original['EXCLUDE_OBJECT_START'](cmd)
        return result

    def change_tool(self, gcmd):
        if self.depth or not self.sd.is_cmd_from_sd():
            return self.physical(self.original['CHANGE_TOOL'], gcmd)
        self.upcoming = self.upcoming_object()
        if self.upcoming in self.exclude.excluded_objects:
            self.pending = (gcmd.get_commandline(), dict(gcmd.get_command_parameters()))
            self.pending_temp = None
            self.skipped += 1
            logging.info('Exclude tool guard: deferred CHANGE_TOOL for %s params=%s', self.upcoming, self.pending[1])
            return
        self.pending = self.pending_temp = None
        return self.physical(self.original['CHANGE_TOOL'], gcmd)

    def temperature(self, gcmd):
        # Heater-off commands and all temperatures inside machine macros always execute.
        target = gcmd.get_float('S', 0.)
        blocked = (self.upcoming in self.exclude.excluded_objects
                   or self.exclude.current_object in self.exclude.excluded_objects)
        if not self.depth and self.sd.is_cmd_from_sd() and blocked and target > 0:
            self.pending_temp = (gcmd.get_command(), gcmd.get_commandline(), dict(gcmd.get_command_parameters()))
            return
        return self.original[gcmd.get_command()](gcmd)

    def start_object(self, gcmd):
        name = gcmd.get('NAME').upper()
        self.upcoming = None
        if not self.depth and self.sd.is_cmd_from_sd() and name not in self.exclude.excluded_objects:
            if self.pending is not None:
                line, params = self.pending
                cmd = self.gcode.create_gcode_command('CHANGE_TOOL', line, params)
                self.physical(self.original['CHANGE_TOOL'], cmd)
                self.pending = None
                self.replayed += 1
                logging.info('Exclude tool guard: applied deferred tool for included object %s', name)
            if self.pending_temp is not None:
                command, line, params = self.pending_temp
                self.original[command](self.gcode.create_gcode_command(command, line, params))
                self.pending_temp = None
        return self.original['EXCLUDE_OBJECT_START'](gcmd)

def load_config(config):
    return ExcludeToolGuard(config)
