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


def feature_macros(text):
    """Add control hooks only; preserve model-specific pins and motion lines."""
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

    once('variable_active_tool: -1', 'variable_tc_count: 0\nvariable_tc_total: 0\nvariable_active_tool: -1')
    once('    SAVE_GCODE_STATE NAME=FAST_CANCEL_CHANGE_TOOL_STATE',
         '    SET_GCODE_VARIABLE MACRO=TOOL_STATE VARIABLE=tc_count VALUE={st.tc_count|int + 1}\n'
         '    PRINT_SENSOR_GATE ENABLE=0\n    SAVE_GCODE_STATE NAME=FAST_CANCEL_CHANGE_TOOL_STATE')
    once('    RESET_FIRSTDOCK_FLAGS',
         '    SET_GCODE_VARIABLE MACRO=TOOL_STATE VARIABLE=tc_count VALUE=0\n'
         '    SET_GCODE_VARIABLE MACRO=TOOL_STATE VARIABLE=tc_total VALUE={params.TC_TOTAL|default(0)|int}\n'
         '    RESET_FIRSTDOCK_FLAGS')
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
