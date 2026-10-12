import re


def macros(text):
    text = re.sub(r'^    LUGO_CANCEL_PHASE[^\n]*\n', '', text, flags=re.M)
    def edit(name, change):
        nonlocal text
        pattern = r'(?ms)^\[gcode_macro ' + re.escape(name) + r'\]\n.*?(?=^\[|\Z)'
        match = re.search(pattern, text)
        if not match:
            raise ValueError('Missing macro ' + name)
        text = text[:match.start()] + change(match.group()) + text[match.end():]
    edit('START_PRINT', lambda b: b.replace('gcode:\n', 'gcode:\n    LUGO_CANCEL_PHASE PHASE=normal TOOL=-1\n', 1))
    for tool in range(4):
        def dock(block, tool=tool):
            lines = block.rstrip().splitlines()
            # The first movement is after the initial temperature wait.
            index = next(i for i, line in enumerate(lines) if line.strip().startswith('G1 '))
            if not any('TEMPERATURE_WAIT' in line for line in lines[:index]):
                raise ValueError('Docking preheat layout changed')
            lines.insert(index, f'    LUGO_CANCEL_PHASE PHASE=docking TOOL={tool}')
            # Extended Klipper commands require KEY=value, unlike native G4 P...
            # Also repair the already-installed legacy spelling on reinstall.
            lines = [re.sub(r'^(\s*)(?:G4|LUGO_CANCEL_WAIT)\s+P\s*=?\s*(.+)$',
                            r'\1LUGO_CANCEL_WAIT P=\2', line) for line in lines]
            lines.extend([f'    LUGO_CANCEL_PHASE PHASE=docked TOOL={tool}', ''])
            return '\n'.join(lines) + '\n'
        edit('DOCK_TOOL_' + str(tool), dock)
        def park(block, tool=tool):
            block = block.replace('gcode:\n', f'gcode:\n    LUGO_CANCEL_PHASE PHASE=parking TOOL={tool}\n', 1)
            return block.rstrip() + f'\n    LUGO_CANCEL_PHASE PHASE=empty TOOL={tool}\n\n'
        edit('PARK_TOOL_' + str(tool), park)
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
