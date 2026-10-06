"""Print-scoped four-tool temperature overrides. Manual-test extension."""
import csv
import math
import re


def metadata(path):
    """Read Orca config comments at either end; never execute file contents."""
    values = {}
    if path:
        with open(path, 'rb') as stream:
            head = stream.read(262144)
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - 262144))
            text = (head + b'\n' + stream.read()).decode('utf-8', 'replace')
        for line in text.splitlines():
            match = re.match(r';\s*(filament_settings_id|lugo_tool_materials|filament_type|nozzle_temperature|nozzle_temperature_initial_layer)\s*=\s*(.*)$', line)
            if match:
                raw = match[2]
                delimiter = ',' if match[1].startswith('nozzle_temperature') else ';'
                values[match[1]] = next(csv.reader([raw], delimiter=delimiter, escapechar='\\'))
    return values


def used_tools(path, yield_scan=None):
    """Find executed tool selections, not the slicer's registered profile list."""
    if not path:
        return None
    used = set()
    command = re.compile(rb'^\s*(?:N\d+\s+)?(START_PRINT|CHANGE_TOOL|T[0-3])(?=\s|\*|$)', re.I)
    with open(path, 'rb') as stream:
        for count, line in enumerate(stream):
            code = line.split(b';', 1)[0]
            match = command.match(code)
            if match:
                name = match[1].upper()
                if name.startswith(b'T'):
                    used.add(int(name[1:]))
                else:
                    key = b'INITIAL_TOOL' if name == b'START_PRINT' else b'NEXT_TOOL'
                    param = re.search(rb'\b' + key + rb'\s*=\s*([0-3])(?=\s|\*|$)', code, re.I)
                    if param:
                        used.add(int(param[1]))
                    elif name == b'START_PRINT':
                        used.add(0)
            if yield_scan and count % 4096 == 4095:
                yield_scan()
    return sorted(used)


class ToolTemperature:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.original = {}
        self.depth = 0
        self.reset()
        self.printer.register_event_handler('klippy:ready', self.connect)
        self.printer.register_event_handler('klippy:shutdown', self.reset)
        self.gcode.register_command('LUGO_SET_TOOL_TEMP', self.set_temperature)

    def reset(self, *args):
        self.active = False
        self.materials = ['Unknown'] * 4
        self.base = [None] * 4
        self.overrides = [None] * 4
        self.used = None

    def connect(self):
        for name in ('START_PRINT', 'CHANGE_TOOL', 'END_PRINT', 'CANCEL_PRINT', 'M104', 'M109'):
            handler = self.gcode.register_command(name, None)
            if handler is None:
                raise self.printer.config_error('Required command missing: ' + name)
            self.original[name] = handler
            self.gcode.register_command(name, lambda cmd, n=name: self.dispatch(n, cmd))

    def tool(self):
        state = self.printer.lookup_object('gcode_macro TOOL_STATE')
        return int(state.get_status(self.printer.get_reactor().monotonic())['active_tool'])

    def replaced(self, cmd, key, value):
        params = dict(cmd.get_command_parameters())
        params[key] = str(value)
        # Macro handlers use rawparams as well as parsed parameters.
        line = cmd.get_command() + ' ' + ' '.join('%s=%s' % item for item in params.items())
        return self.gcode.create_gcode_command(cmd.get_command(), line, params)

    def begin(self):
        self.reset()
        self.active = True
        sd = self.printer.lookup_object('virtual_sdcard', None)
        try:
            data = metadata(sd.file_path() if sd else None)
            reactor = self.printer.get_reactor()
            self.used = used_tools(sd.file_path() if sd else None,
                                   lambda: reactor.pause(reactor.monotonic()))
            for i, name in enumerate(data.get('filament_settings_id', data.get('lugo_tool_materials', data.get('filament_type', [])))[:4]):
                self.materials[i] = name or 'Unknown'
            for i, value in enumerate(data.get('nozzle_temperature', [])[:4]):
                temp = float(value)
                if math.isfinite(temp) and temp > 0:
                    self.base[i] = temp
        except (OSError, ValueError, csv.Error):
            self.gcode.respond_info('Tool temperature: metadata unavailable; toolchange temperatures will be used.')

    def dispatch(self, name, cmd):
        if name == 'START_PRINT':
            self.begin()
            initial = cmd.get_int('INITIAL_TOOL', minval=0, maxval=3) if 'INITIAL_TOOL' in cmd.get_command_parameters() else 0
            if self.used is not None and initial not in self.used:
                self.used.append(initial)
            if 'EXTRUDER_TEMP' in cmd.get_command_parameters():
                self.base[initial] = cmd.get_float('EXTRUDER_TEMP')
        if name in ('END_PRINT', 'CANCEL_PRINT'):
            # Clear even if the existing end/park macro subsequently fails.
            self.reset()
        if name == 'CHANGE_TOOL' and self.active:
            tool = cmd.get_int('NEXT_TOOL', minval=0, maxval=3)
            if self.used is not None and tool not in self.used:
                self.used.append(tool)
            self.base[tool] = cmd.get_float('TEMP', minval=0)
            if self.overrides[tool] is not None:
                cmd = self.replaced(cmd, 'TEMP', self.overrides[tool])
        if name in ('M104', 'M109') and self.active and not self.depth:
            tool = self.tool()
            # S0 always remains an off command. Toolchange heating boosts pass through.
            if 0 <= tool < 4 and cmd.get_float('S', 0) > 0:
                self.base[tool] = cmd.get_float('S')
                if self.overrides[tool] is not None:
                    cmd = self.replaced(cmd, 'S', self.overrides[tool])
        nested = name in ('START_PRINT', 'CHANGE_TOOL', 'END_PRINT', 'CANCEL_PRINT')
        self.depth += int(nested)
        try:
            result = self.original[name](cmd)
            if name == 'CHANGE_TOOL' and self.active:
                # A UI request may arrive while TEMPERATURE_WAIT yields.
                tool = self.tool()
                if 0 <= tool < 4 and self.overrides[tool] is not None:
                    heater = self.printer.lookup_object('extruder').get_heater()
                    self.printer.lookup_object('heaters').set_temperature(heater, self.overrides[tool], False)
            return result
        except Exception:
            if name == 'START_PRINT':
                self.reset()
            raise
        finally:
            self.depth -= int(nested)

    def set_temperature(self, cmd):
        if not self.active:
            raise cmd.error('No active print temperature session')
        tool = cmd.get_int('TOOL', minval=0, maxval=3)
        if self.used is not None and tool not in self.used:
            raise cmd.error('This tool is not used in the current print')
        heater = self.printer.lookup_object('extruder').get_heater()
        # Existing LUGOWARE docking adds up to 40 C.
        maximum = heater.max_temp - 40
        value = cmd.get_float('TEMP', minval=max(1, heater.min_temp), maxval=maximum)
        if not math.isfinite(value):
            raise cmd.error('Invalid temperature')
        self.overrides[tool] = value
        if self.tool() == tool and not self.depth:
            self.printer.lookup_object('heaters').set_temperature(heater, value, False)
        cmd.respond_info('T%d print temperature: %.1f C' % (tool + 1, value))

    def get_status(self, eventtime):
        stats = self.printer.lookup_object('print_stats', None)
        if self.active and stats and stats.get_status(eventtime)['state'] in ('complete', 'cancelled', 'error'):
            self.reset()
        used = [None if self.used is None else i in self.used for i in range(4)]
        return {'active': self.active, 'used': used,
                'materials': [name if used[i] is not False else '' for i, name in enumerate(self.materials)],
                'base': list(self.base), 'overrides': list(self.overrides),
                'temperatures': [(o if o is not None else b) if used[i] is not False else None
                                 for i, (o, b) in enumerate(zip(self.overrides, self.base))]}


def load_config(config):
    return ToolTemperature(config)
