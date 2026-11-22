import re


def macros(text):
    # Model branches now ship the reviewed final macros. Do not regenerate old
    # docking code or overwrite customer-edited coordinates in a post-merge hook.
    required = ['CANCEL_PRINT', '_FAST_CANCEL_MOTION', '_FAST_CANCEL_RETURN',
                '_FAST_CANCEL_FINALIZE', 'PAUSE', 'RESUME']
    for name in required:
        if '[gcode_macro ' + name + ']' not in text:
            raise ValueError('Update the model configuration before installing fast_cancel: ' + name)
    if re.search(r'^\s*LUGO_CANCEL_', text, re.M):
        raise ValueError('Legacy and current cancellation commands are mixed; use the latest model configuration')
    for tool in range(4):
        for marker in [f'FAST_CANCEL_PRIME STATE=begin TOOL={tool}',
                       f'FAST_CANCEL_PRIME STATE=end TOOL={tool}',
                       f'FAST_CANCEL_PHASE PHASE=docked TOOL={tool}']:
            if marker not in text:
                raise ValueError('Missing final cancellation marker: ' + marker)
    return text


def prepare_macros(text):
    if 'LUGO_CONFIRMED_EMPTY_SLOT' in text:
        return text
    start = text.index('[gcode_macro PREPARE_ACTION]')
    end = text.index('[gcode_macro _PREPARE_VERIFY]', start)
    block = text[start:end]
    old = "    {% set manual = active == -1 and sensed and action in ['PARK', 'PRIME'] %}"
    new = old + '''
    # LUGO_CONFIRMED_EMPTY_SLOT: operator inspection, not automatic occupancy detection.
    {% set cross = active in [0, 1, 2, 3] and tool != active and action in ['PARK', 'PRIME'] %}
    {% set confirmed = params.CONFIRM_EMPTY|default(0)|int == 1 and params.FROM_TOOL|default(-2)|int == active %}
    {% if cross and not confirmed %}
        {action_raise_error('Confirm the destination station is empty and the mounted tool is unchanged.')}
    {% endif %}'''
    guard = "    {% if action != 'MOTOR_OFF' and active != -1 and (action not in ['PARK', 'PRIME', 'EXTRUDE'] or tool != active) %}"
    route = '    M221 S100\n'
    for needle in (old, guard, route):
        if block.count(needle) != 1:
            raise ValueError('Unexpected PREPARE_ACTION layout')
    block = block.replace(old, new).replace(guard, guard.replace('tool != active)', '(tool != active and not (cross and confirmed)))'))
    block = block.replace(route, route + '''    {% if cross %}
        HOME_CHECK
        G1 X230 F6000
        SET_GCODE_VARIABLE MACRO=PREPARE_STATE VARIABLE=last_tool VALUE={tool}
    {% endif %}
''')
    return text[:start] + block + text[end:]


def _feature_macros(text):
    """Add control hooks only; preserve model-specific pins and motion lines."""
    from october_features import config
    text = config(text)
    if '[gcode_macro START_PRINT]' not in text:
        return text
    if 'PRINT_SENSOR_BEGIN' in text:
        for marker in ('PRINT_SENSOR_END', 'PRINT_SENSOR_GATE', 'variable_tc_count:', 'variable_tc_total:'):
            if marker not in text:
                raise ValueError('Incomplete print features: ' + marker)
        return text

    def once(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('Unsupported print feature anchor: ' + old)
        text = text.replace(old, new, 1)

    def edit(name, transform):
        nonlocal text
        pattern = r'(\[gcode_macro ' + re.escape(name) + r'\]\n)(.*?)(?=\n\[|\Z)'
        match = re.search(pattern, text, re.S)
        if not match:
            raise ValueError('Missing macro: ' + name)
        text = text[:match.start()] + match[1] + transform(match[2]) + text[match.end():]

    additions = ''.join('variable_' + name + ': 0\n' for name in ('tc_count', 'tc_total')
                        if not re.search(r'^variable_' + name + r'\s*:', text, re.M))
    if additions:
        once('variable_active_tool: -1', additions + 'variable_active_tool: -1')
    change = re.search(r'(?s)\[gcode_macro CHANGE_TOOL\].*?(?=\n\[|\Z)', text).group()
    increment = '' if 'VARIABLE=tc_count ' in change else '    SET_GCODE_VARIABLE MACRO=TOOL_STATE VARIABLE=tc_count VALUE={st.tc_count|int + 1}\n'
    once('    SAVE_GCODE_STATE NAME=FAST_CANCEL_CHANGE_TOOL_STATE',
         increment + '    PRINT_SENSOR_GATE ENABLE=0\n    SAVE_GCODE_STATE NAME=FAST_CANCEL_CHANGE_TOOL_STATE')
    start = re.search(r'(?s)\[gcode_macro START_PRINT\].*?(?=\n\[|\Z)', text).group()
    reset = ''
    if 'VARIABLE=tc_count ' not in start:
        reset += '    SET_GCODE_VARIABLE MACRO=TOOL_STATE VARIABLE=tc_count VALUE=0\n'
    if 'VARIABLE=tc_total ' not in start:
        reset += '    SET_GCODE_VARIABLE MACRO=TOOL_STATE VARIABLE=tc_total VALUE={params.TC_TOTAL|default(0)|int}\n'
    if reset:
        once('    RESET_FIRSTDOCK_FLAGS', reset + '    RESET_FIRSTDOCK_FLAGS')
    text = re.sub(r'SET_FILAMENT_SENSOR SENSOR=encoder_sensor ENABLE=[01]', 'PRINT_SENSOR_GATE ENABLE=0', text)
    edit('START_PRINT', lambda b: b.replace('gcode:\n', 'gcode:\n    PRINT_SENSOR_BEGIN\n', 1).replace(
        '    SET_FILAMENT_SENSOR SENSOR=toolhead_sensor ENABLE=0',
        '    SET_FILAMENT_SENSOR SENSOR=toolhead_sensor ENABLE=0\n    PRINT_SENSOR_GATE ENABLE=1'))
    edit('CHANGE_TOOL', lambda b: b.rstrip() + '\n    PRINT_SENSOR_GATE ENABLE=1\n\n')
    edit('PAUSE', lambda b: b.replace('gcode:\n', 'gcode:\n    PRINT_SENSOR_GATE ENABLE=0\n', 1))
    def resume(b):
        b, count = re.subn(r'(?m)^(\s*)BASE_RESUME\s*$', r'\1BASE_RESUME\n\1PRINT_SENSOR_GATE ENABLE=1', b)
        if count != 1:
            raise ValueError('Missing resume gate anchor')
        return b
    edit('RESUME', resume)
    for name in ('END_PRINT', 'CANCEL_PRINT'):
        edit(name, lambda b: b.replace('gcode:\n', 'gcode:\n    PRINT_SENSOR_END\n', 1))
    return text


def feature_macros(text):
    from mesh_features import config
    return cancel_return_wait(end_print_autosave(config(_feature_macros(text))))


def prepare_extrusion_distance(text):
    section = re.search(r'(?ms)^\[gcode_macro PREPARE_ACTION\][^\n]*\n.*?(?=^\[|\Z)', text)
    if not section:
        return text
    old = 'G1 E{10.0 * factor} F{8.0 * 60 / (3.141592653589793 * (dia / 2) ** 2)}'
    move = re.compile(r'^([ \t]+)' + re.escape(old) + r'([ \t]*)$', re.M)
    if len(move.findall(section[0])) != 1:
        return text
    new = old.replace('10.0 * factor', '20.0 * factor')
    block = move.sub(lambda line: line[1] + new + line[2], section[0])
    return text[:section.start()] + block + text[section.end():]


def cancel_return_wait(text):
    section = re.search(r'(?ms)^\[gcode_macro _FAST_CANCEL_MOTION\][^\n]*\n.*?(?=^\[|\Z)', text)
    if section is None or 'FAST_CANCEL_WAIT_DETACH' in section[0]:
        return text
    block, count = re.subn(r'(?m)^([ \t]+)(_FAST_CANCEL_RETURN\b[^\n]*)$',
                           r'\1FAST_CANCEL_WAIT_DETACH\n\1\2', section[0])
    if count > 1:
        raise ValueError('Unable to locate the cancel return command')
    return text[:section.start()] + block + text[section.end():]


def end_print_autosave(text):
    section = re.search(r'(?m)^\[gcode_macro END_PRINT\][^\n]*\n.*?(?=^\[|\Z)',
                        text, re.S)
    if not section:
        return text
    block = re.sub(r'(?m)^([ \t]*Z_OFFSET_APPLY_PROBE[ \t]*\n[ \t]*SAVE_CONFIG)[ \t]*$',
                   r'\1 LUGO_FIRMWARE_RESTART=1', section[0], count=1)
    return text[:section.start()] + block + text[section.end():]
SAVE_CONFIG_START = '    def cmd_SAVE_CONFIG(self, gcmd):\n'
SAVE_CONFIG_RESTART = "        gcode.request_restart('restart')\n"
AUTOSAVE_OPTION = "        firmware_restart = gcmd.get_int('LUGO_FIRMWARE_RESTART', 0, minval=0, maxval=1)\n"
AUTOSAVE_RESTART = (
    "        if firmware_restart:\n"
    "            if not self.printer.is_shutdown():\n"
    "                gcode.request_restart('firmware_restart')\n"
    "        else:\n"
    "            gcode.request_restart('restart')\n"
)


def save_config_patch(text):
    before, start, remainder = text.partition(SAVE_CONFIG_START)
    body, end, after = remainder.partition('\n    def ')
    if not start:
        raise ValueError('Unsupported Klipper SAVE_CONFIG implementation')
    if body.startswith(AUTOSAVE_OPTION) and AUTOSAVE_RESTART in body:
        return text
    save_position = body.find('os.rename(temp_name, cfgname)')
    if (body.count(SAVE_CONFIG_RESTART) != 1
            or not 0 <= save_position < body.index(SAVE_CONFIG_RESTART)):
        raise ValueError('Unsupported Klipper SAVE_CONFIG restart path')
    body = AUTOSAVE_OPTION + body.replace(SAVE_CONFIG_RESTART, AUTOSAVE_RESTART, 1)
    return before + start + body + end + after
