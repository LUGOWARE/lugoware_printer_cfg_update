"""Defer tool changes for excluded objects; keep machine macros outside exclusion."""
import logging
import math
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
        self.printer.lookup_object('webhooks').register_endpoint('exclude_tool_guard/request', self.handle_request)

    def reset(self):
        self.pending = None
        self.pending_temp = None
        self.upcoming = None
        self.skipped = 0
        self.replayed = 0
        self.filtered_wipe_gaps = 0
        self.startup_active = False
        self.startup_excludes = []
        self.first_object = self.first_tool = None

    def ready(self):
        self.sd = self.printer.lookup_object('virtual_sdcard')
        self.exclude = self.printer.lookup_object('exclude_object')
        reactor = self.printer.get_reactor()
        reactor.register_timer(self.flush_pending, reactor.monotonic() + .25)
        self.original = {}
        handlers = {'START_PRINT': self.start_print, 'CHANGE_TOOL': self.change_tool,
                    'EXCLUDE_OBJECT_START': self.start_object,
                    'EXCLUDE_OBJECT_END': self.end_object,
                    'M104': self.temperature, 'M109': self.temperature}
        for name, handler in handlers.items():
            old = self.gcode.register_command(name, None)
            if old is None:
                raise self.printer.config_error('exclude_tool_guard requires ' + name)
            self.original[name] = old
            self.gcode.register_command(name, handler)
        self.gcode.register_command('EXCLUDE_TOOL_PREPARE', self.prepare_first)
        self.original_run_script = self.gcode.run_script
        self.gcode.run_script = self.external_script
        # Cancellation/parking must remain real movement even if an object is excluded.
        for name in ('PARK_CURRENT', 'DOCK_TOOL_0', 'DOCK_TOOL_1', 'DOCK_TOOL_2',
                     'DOCK_TOOL_3', '_FAST_CANCEL_MOTION', '_FAST_CANCEL_RETURN',
                     'CANCEL_PRINT', 'END_PRINT'):
            old = self.gcode.register_command(name, None)
            if old is not None:
                self.gcode.register_command(name, lambda cmd, fn=old: self.physical(fn, cmd))

    def get_status(self, eventtime):
        return {'skipped_toolchanges': self.skipped, 'deferred_toolchange': self.pending is not None,
                'replayed_toolchanges': self.replayed, 'upcoming_object': self.upcoming,
                'filtered_wipe_gaps': self.filtered_wipe_gaps,
                'startup_excludes': list(self.startup_excludes),
                'pending_excludes': list(self.startup_excludes),
                'first_object': self.first_object, 'first_tool': self.first_tool}

    def start_print(self, gcmd):
        self.startup_active = True
        self.startup_excludes = []
        self.first_object = None
        self.first_tool = None
        try:
            return self.original['START_PRINT'](gcmd)
        finally:
            self.startup_active = False

    def external_script(self, script):
        # Only defer a standalone, validated exclusion request. No movement or
        # heater command bypasses the normal G-code mutex.
        match = re.fullmatch(r'\s*EXCLUDE_OBJECT\s+NAME=([^\s;]+)\s*', script, re.I)
        if (self.startup_active or self.depth) and match:
            name = match.group(1).upper()
            known = {obj['name'].upper() for obj in self.exclude.objects}
            if name in known:
                self.queue_exclusion(name)
                return
        return self.original_run_script(script)

    def queue_exclusion(self, name):
        name = name.upper()
        known = {obj['name'].upper() for obj in self.exclude.objects}
        if name not in known:
            raise self.gcode.error('Unknown object')
        if name in self.exclude.excluded_objects:
            return 'excluded'
        if name in self.startup_excludes:
            return 'pending'
        if len(known - set(self.exclude.excluded_objects) - set(self.startup_excludes)) <= 1:
            raise self.gcode.error('Cannot exclude the last object; cancel the print instead')
        self.startup_excludes.append(name)
        logging.info('Exclude tool guard: queued exclusion %s', name)
        return 'pending'

    def handle_request(self, request):
        name = request.get_str('name').upper()
        action = request.get_str('action', 'exclude')
        if action == 'cancel':
            # Never issue RESET / unexclude after actual application.
            if name in self.startup_excludes:
                self.startup_excludes.remove(name)
                state = 'normal'
            else:
                state = 'excluded' if name in self.exclude.excluded_objects else 'normal'
        elif action == 'exclude':
            stats = self.printer.lookup_object('print_stats').get_status(self.printer.get_reactor().monotonic())
            if stats['state'] not in ('printing', 'paused'):
                raise request.error('No active print')
            try:
                state = self.queue_exclusion(name)
            except self.printer.command_error as exc:
                raise request.error(str(exc))
        else:
            raise request.error('Unknown exclusion action')
        request.send({'name': name, 'state': state})

    def flush_pending(self, eventtime):
        if self.startup_excludes:
            fc = self.printer.lookup_object('fast_cancel')
            stats = self.printer.lookup_object('print_stats').get_status(eventtime)
            if self.printer.is_shutdown() or fc.requested or fc.cleaning or stats['state'] not in ('printing', 'paused'):
                self.startup_excludes = []
            elif not self.startup_active and not self.depth:
                with self.gcode.get_mutex():
                    # Recheck after acquiring the mutex; a request may have been
                    # withdrawn or a machine macro may have started while waiting.
                    stats = self.printer.lookup_object('print_stats').get_status(self.printer.get_reactor().monotonic())
                    if not self.startup_active and not self.depth and not fc.requested and not fc.cleaning and stats['state'] in ('printing', 'paused'):
                        self.apply_startup_excludes()
        return eventtime + .25

    def apply_startup_excludes(self):
        pending, self.startup_excludes = self.startup_excludes, []
        for name in pending:
            self.gcode.run_script_from_command('EXCLUDE_OBJECT NAME=' + shlex.quote(name))

    @staticmethod
    def tool_params(line):
        tokens = shlex.split(line)
        params = {}
        for token in tokens[1:]:
            key, sep, value = token.partition('=')
            if not sep or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', key):
                raise ValueError('Unsupported first tool parameters')
            params[key.upper()] = value
        return params

    def select_first(self, defaults, gcmd):
        excluded = set(self.exclude.excluded_objects)
        if not excluded:
            return None, dict(defaults)
        path = self.sd.file_path()
        if not path or not self.sd.is_cmd_from_sd():
            raise gcmd.error('First tool selection requires an active print file')
        prepared = self.printer.lookup_object('lugo_preanalysis', None)
        prepared = prepared.for_file(path) if prepared else None
        if prepared:
            params = dict(defaults)
            start = self.sd.get_file_position()
            for offset, line in prepared['first_commands']:
                if offset < start: continue
                if offset - start > 32 * 1024 * 1024:
                    raise gcmd.error('Cannot determine first printable tool within scan limit')
                command = line.split()[0].upper()
                if command == 'CHANGE_TOOL': params = self.tool_params(line)
                elif command in ('M104', 'M109'):
                    match = re.search(r'(?:^|\s)S([-+0-9.eE]+)', line, re.I)
                    if match: params['TEMP'] = match.group(1)
                elif re.fullmatch(r'T\d+', command):
                    if int(command[1:]) != int(params.get('NEXT_TOOL', -1)):
                        raise gcmd.error('First printable tool has no matching CHANGE_TOOL settings')
                elif command == 'EXCLUDE_OBJECT_START':
                    match = NAME.search(line)
                    if not match: raise gcmd.error('First printable object has no name')
                    name = match.group(1).upper()
                    if name not in excluded: return name, params
                elif command in ('END_PRINT', 'PRINT_END', 'START_PRINT'): break
            raise gcmd.error('No printable object remains or first tool settings are unavailable')
        params = dict(defaults)
        count = 0
        checkpoint = 65536
        with open(path, 'rb') as stream:
            stream.seek(self.sd.get_file_position())
            while True:
                raw = stream.readline(65537)
                if not raw:
                    break
                count += len(raw)
                if len(raw) > 65536 or count > 32 * 1024 * 1024:
                    raise gcmd.error('Cannot determine first printable tool within scan limit')
                if count >= checkpoint:
                    reactor = self.printer.get_reactor()
                    reactor.pause(reactor.monotonic())
                    checkpoint = count + 65536
                line = raw.decode('utf-8', errors='replace').split(';', 1)[0].strip()
                if not line:
                    continue
                command = line.split()[0].upper()
                if command == 'CHANGE_TOOL':
                    # Start from this exact material's settings, not the excluded
                    # first material's defaults. CHANGE_TOOL supplies its own defaults.
                    try:
                        params = self.tool_params(line)
                    except ValueError as exc:
                        raise gcmd.error(str(exc))
                elif command in ('M104', 'M109'):
                    match = re.search(r'(?:^|\s)S([-+0-9.eE]+)', line, re.I)
                    if match:
                        params['TEMP'] = match.group(1)
                elif re.fullmatch(r'T\d+', command):
                    if int(command[1:]) != int(params.get('NEXT_TOOL', -1)):
                        raise gcmd.error('First printable tool has no matching CHANGE_TOOL settings')
                elif command == 'EXCLUDE_OBJECT_START':
                    match = NAME.search(line)
                    if not match:
                        raise gcmd.error('First printable object has no name')
                    name = match.group(1).upper()
                    if name not in excluded:
                        return name, params
                elif command in ('END_PRINT', 'PRINT_END', 'START_PRINT'):
                    break
        raise gcmd.error('No printable object remains or first tool settings are unavailable')

    def prepare_first(self, gcmd):
        if not self.startup_active:
            raise gcmd.error('EXCLUDE_TOOL_PREPARE is only available inside START_PRINT')
        approach_x = gcmd.get_float("APPROACH_X", 230.)
        approach_f = gcmd.get_float("APPROACH_F", 9000., above=0.)
        defaults = dict(gcmd.get_command_parameters())
        defaults.pop("APPROACH_X", None)
        defaults.pop("APPROACH_F", None)
        while True:
            self.apply_startup_excludes()
            name, params = self.select_first(defaults, gcmd)
            if self.startup_excludes:
                continue  # A request arrived while scanning; use the latest set.
            try:
                tool = int(params['NEXT_TOOL'])
                temperature = float(params['TEMP'])
            except (KeyError, ValueError):
                raise gcmd.error('Invalid first printable tool settings')
            if tool not in range(4) or not math.isfinite(temperature) or temperature <= 0:
                raise gcmd.error('Invalid first printable tool or temperature')
            fc = self.printer.lookup_object('fast_cancel')
            if fc.requested or fc.cleaning or self.printer.is_shutdown():
                self.printer.lookup_object('heaters').turn_off_all_heaters()
                return  # Let fast_cancel unwind normally; never enter SD error handling.
            # Material-dependent wait used to be rendered with INITIAL_TOOL's
            # temperature. Resolve it here, after accepting startup exclusions.
            self.gcode.run_script_from_command(
                'M104 S%g\nTEMPERATURE_WAIT SENSOR=extruder MINIMUM=%g MAXIMUM=%g'
                % (temperature, temperature - 5, temperature + 20))
            if fc.requested or fc.cleaning or self.printer.is_shutdown():
                self.printer.lookup_object('heaters').turn_off_all_heaters()
                return  # Let fast_cancel unwind normally; never enter SD error handling.
            if self.startup_excludes:
                continue  # Includes exclusions submitted during final heating.
            break
        self.first_object, self.first_tool = name, tool
        logging.info('Exclude tool guard: initial tool=%d object=%s params=%s excluded=%s',
                     tool, name, params, self.exclude.excluded_objects)
        # From here docking is committed. Later requests use normal serialization.
        self.gcode.run_script_from_command('G1 X%g F%g' % (approach_x, approach_f))
        if fc.requested or fc.cleaning or self.printer.is_shutdown():
            self.printer.lookup_object('heaters').turn_off_all_heaters()
            return
        self.startup_active = False
        self.pending = self.pending_temp = self.upcoming = None
        line = 'CHANGE_TOOL ' + ' '.join(key + '=' + shlex.quote(str(value))
                                        for key, value in params.items())
        cmd = self.gcode.create_gcode_command('CHANGE_TOOL', line, params)
        return self.physical(self.original['CHANGE_TOOL'], cmd)

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
