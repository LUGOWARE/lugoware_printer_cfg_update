"""M5P opt-in auxiliary heater profile. Pure planning before transactional writes."""
import argparse
import ast
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import paused_tool_service_hooks as paused_tools
from install_panels import TOOL_CARD_RUNTIME, runtime_payload
from patch_print_controls import prepare_extrusion_distance

SINGLE_HEATER = 'toolhead_single'
VARIANTS = ('standard', 'toolhead', SINGLE_HEATER)
SENSOR = 'temperature_toolhead_sensor toolhead_sensor'
AUX = ('toolhead_auxiliary', 'heater_generic Toolhead')
LEGACY_AUX_SENSOR = 'toolhead_temperature_test'
TOOLHEAD_MODULES = ('toolhead_auxiliary.py', 'toolhead_temperature_test.py',
                    'temperature_toolhead_sensor.py', 'detachable_heater_sensor.py',
                    'lugo_dock_recovery.py')
NOZZLE_PID = dict(control='pid', pid_kp='13.953', pid_ki='0.511', pid_kd='95.230')
TOOLHEAD_PID = dict(control='pid', pid_kp='37.681', pid_ki='9.191', pid_kd='38.623')
SINGLE_NOZZLE_PID = dict(control='pid', pid_kp='25.304', pid_ki='1.231', pid_kd='129.999')
SINGLE_TOOLHEAD_PID = dict(control='pid', pid_kp='29.327', pid_ki='3.153', pid_kd='68.185')
TOOLHEAD_TUNING = ('prime_temperature_margin', 'prime_timeout', 'park_nozzle_preheat_offset')
LEGACY_NOZZLE_OFFSETS = ('nozzle_temperature_offset', 'nozzle_offset_threshold', 'nozzle_offset_max_temp')
RESUME_DOCK_HOLD = "{% if printer.fast_cancel.phase == 'dock_sensor_hold' %}"
RESUME_PAUSED = '{% if printer.pause_resume.is_paused %}'
RESUME_DOCK_MESSAGE = '{action_raise_error("Inspect the tool at the dock and cancel the held print before moving.")}'
RESUME_DOCK_CONFIRM = (
    '{% if params.DOCK_CONFIRMED|default(0)|int > 0 %}',
    '  TOOLHEAD_RESUME_DOCK CONFIRMED={params.DOCK_CONFIRMED|int}',
    '{% else %}',
    '  {action_respond_info("Use the printer screen to confirm the tool is parked before resuming.")}',
    '{% endif %}',
)


def strip_dock_routes(text):
    for slot in range(1, 5):
        for action in ('PARK', 'DOCK'):
            text = remove_section(text, 'gcode_macro _T%d_RETRY_%s_XY' % (slot, action))
            text = remove_section(text, 'gcode_macro _TOOL_RETRY_%s_XY_T%d' % (action, slot))
    return text


def remove_dock_retry(text):
    text = strip_dock_routes(text)
    alternate = '|'.join(r'\n'.join(r'[ \t]+' + re.escape(l.lstrip()) for l in body)
                         for body in ((RESUME_DOCK_MESSAGE,), RESUME_DOCK_CONFIRM))
    guard = r'(?m)^([ \t]*)' + re.escape(RESUME_DOCK_HOLD) + r'\n(?:' + alternate + ')'
    guard += r'\n[ \t]*' + re.escape(RESUME_PAUSED.replace(' if ', ' elif '))
    return re.sub(guard, lambda m: m[1] + RESUME_PAUSED, text)


def xy_feed_moves(lines):
    moves = []
    for line in lines:
        code = line.split(';', 1)[0].strip()
        if not re.match(r'^G1[ \t]+[XY]', code):
            continue
        feed = re.search(r'\bF(\d+)$', code)
        if not feed:
            return []
        coordinates = tuple((axis, float(value)) for axis, value in
                            re.findall(r'\b([XY])(-?\d+(?:\.\d+)?)\b', code))
        moves.append((coordinates, int(feed[1])))
    return moves


def preparation_feeds(text, action, slot, commands):
    # Use preparation feeds only where its normal route matches the verified service path.
    source = section(text, 'gcode_macro %s_%d' % (action.upper(), slot - 1))
    if not source:
        return {}, None
    prepared = xy_feed_moves(source[0].splitlines())
    service = xy_feed_moves(commands)
    if action == 'dock':
        shared = prepared[:-2]
        if (not shared or len(prepared[-2][0]) != 1 or prepared[-2][0][0][0] != 'X'
                or [move[0] for move in shared] != [move[0] for move in service[:len(shared)]]):
            return {}, None
        return {index: move[1] for index, move in enumerate(shared) if index}, prepared[-2][1]
    normal = prepared[-8:-1]
    indices = (0, 3, 4, 6, 7, 8)
    if (len(normal) != 7 or len(service) != 9
            or [normal[index][0] for index in (0, 2, 3, 4, 5, 6)] != [service[index][0] for index in indices]):
        return {}, None
    # Service approaches the second park waypoint in two moves and repeats the seat waypoint.
    return {index: normal[match][1]
            for index, match in enumerate((0, 1, 1, 2, 3, 3, 4, 5, 6)) if index}, None


def add_dock_retry(text, assets):
    text = strip_dock_routes(text)
    release = json.loads((assets / 'dock_retry_paths.json').read_text(encoding='utf-8'))
    moves = []
    for slot in range(4):
        for action in ('DOCK', 'PARK'):
            match = section(text, 'gcode_macro %s_TOOL_%d' % (action, slot))
            if not match:
                return text
            block = match[0]
            moves.extend(' '.join(line.split()) for line in block.splitlines()
                         if re.match(r'^\s*G[01]\s', line))
    signature = hashlib.sha256('\n'.join(moves).encode()).hexdigest()
    delta = release['geometries'].get(signature)
    if delta is None:
        # Keep the sensor check and stationary hold for unrecognized motion paths.
        return text
    blocks = []
    for slot, path in enumerate(release['paths'], 1):
        for action in ('park', 'dock'):
            commands = [re.sub(r'\bX(-?\d+(?:\.\d+)?)', lambda m: 'X%g' % (float(m[1]) + delta), line)
                        for line in path[action]]
            # Klipper ends the command token at the first digit followed by letters.
            block = '[gcode_macro _TOOL_RETRY_%s_XY_T%d]\n' % (action.upper(), slot)
            feeds, exit_feed = preparation_feeds(text, action, slot, commands)
            for index, feed in feeds.items():
                commands[index] = re.sub(
                    r'F(\d+)$', lambda match: f'F{{{feed} if params.SERVICE|default(0)|int else {match[1]}}}',
                    commands[index])
            if action == 'dock':
                if exit_feed is not None:
                    block += f'variable_service_exit_feed: {exit_feed}\n'
                x = float(re.findall(r'\bX(-?[\d.]+)', '\n'.join(commands))[-1])
                y = float(re.findall(r'\bY(-?[\d.]+)', '\n'.join(commands))[-1])
                block += ('variable_retry_x: %s\nvariable_retry_y: %s\nvariable_retry_exit: %r\n'
                          % (x, y, (366. + delta, 361. + delta, 334.5 + delta)))
            # Only the approach is clear of the rack. Automatic recovery uses its original feed.
            commands[0] = re.sub(r'F(\d+)$', r'F{params.APPROACH_F|default(\1)|int}', commands[0])
            blocks.append(block + 'gcode:\n    ' + '\n    '.join(commands + ['M400']) + '\n')
    return text.rstrip() + '\n\n' + '\n'.join(blocks)


def dock_temperature_actions(text, enable):
    # Match only the three auxiliary temperature stages, keeping standard phases reversible.
    gate = '    TOOLHEAD_CHECK_DOCK_READY\n'
    wait = '    # FAST_CANCEL_WAIT P={(h_d * 1000)|int}\n'
    for slot in range(4):
        m = section(text, 'gcode_macro DOCK_TOOL_%d' % slot)
        block = m[0].replace(gate, '')
        block = re.sub(r'(?m)^    TOOLHEAD_PRIME_COMPLETE EXIT_X=[\d.]+\n', '', block)
        block = block.replace('    TOOLHEAD_VERIFY_DOCK_EXIT\n', '    CHECK_TOOL_STATE STATE=ATTACHED\n')
        if enable:
            block = block.replace('    {% set preheat_temp = normal_temp + 20 %}\n', '', 1)
            block = block.replace('    # M104 S{preheat_temp}\n    # TEMPERATURE_WAIT SENSOR=extruder',
                                  '    # TEMPERATURE_WAIT SENSOR=extruder', 1).replace(wait, '', 1)
            block = block.replace('    # M104 S{preheat_temp}\n    TOOLHEAD_DOCK_HEAT',
                                  gate + '    M104 S{preheat_temp}\n    TOOLHEAD_DOCK_HEAT')
            block = block.replace('    {% set preheat_temp = normal_temp %}\n    # M104',
                                  '    {% set preheat_temp = normal_temp %}\n    M104')
            if block.count(gate) != 1:
                raise ValueError('Missing safe preheat gate for DOCK_TOOL_%d' % slot)
            # Drain the final wipe before checking the connector or arming heat.
            phase_start = block.index(gate)
            last_motion = list(re.finditer(r'(?m)^[ \t]+G[0123][ \t]', block[:phase_start]))
            if not last_motion or not re.search(r'(?m)^[ \t]+M400[ \t]*(?:#.*)?$',
                                                block[last_motion[-1].end():phase_start]):
                raise ValueError('Missing final wipe barrier for DOCK_TOOL_%d' % slot)
            block, count = re.subn(r'(?m)^(    FAST_CANCEL_PRIME STATE=end TOOL=%d EXIT_X=([\d.]+)\n)' % slot,
                                   r'\1    TOOLHEAD_PRIME_COMPLETE EXIT_X=\2\n', block)
            if count != 1:
                raise ValueError('Missing prime completion checkpoint for DOCK_TOOL_%d' % slot)
            if block.count('    CHECK_TOOL_STATE STATE=ATTACHED\n') != 1:
                raise ValueError('Missing dock exit check for DOCK_TOOL_%d' % slot)
            block = block.replace('    CHECK_TOOL_STATE STATE=ATTACHED\n', '    TOOLHEAD_VERIFY_DOCK_EXIT\n')
        else:
            block = block.replace('    M104 S{preheat_temp}\n    TOOLHEAD_DOCK_HEAT TEMP={slicer_temp}',
                                  '    # M104 S{preheat_temp}\n    TOOLHEAD_DOCK_HEAT TEMP={slicer_temp}')
            block = block.replace('    {% set preheat_temp = normal_temp %}\n    M104',
                                  '    {% set preheat_temp = normal_temp %}\n    # M104')
            block = re.sub(r'(?m)^(    TOOLHEAD_DOCK_HEAT TEMP=\{slicer_temp\}\n)(?=    TOOLHEAD_WAIT_FOR_PRIME)',
                           lambda match: match[1] + wait, block)
            block = re.sub(r'(?m)^(    TOOLHEAD_DOCK_HEAT TEMP=\{slicer_temp\}\n)'
                           r'    FAST_CANCEL_WAIT P=\{\(h_d \* 1000\)\|int\}\n'
                           r'    #\s*TOOLHEAD_WAIT_FOR_PRIME TARGET=\{slicer_temp\}\n',
                           lambda match: match[1] + wait + '    TOOLHEAD_WAIT_FOR_PRIME TARGET={slicer_temp}\n', block)
            first = '    {% set slicer_temp = params.SLICER_TEMP|default(normal_temp)|int %}\n'
            if first in block and '    {% set preheat_temp = normal_temp + 20 %}\n' not in block:
                block = block.replace(first, first + '    {% set preheat_temp = normal_temp + 20 %}\n', 1)
                block = re.sub(r'(?m)(^    \{% set is_175[^\n]*\n)\n*(    # TEMPERATURE_WAIT SENSOR=extruder)',
                               r'\1\n    # M104 S{preheat_temp}\n\2', block, count=1)
        text = text[:m.start()] + block + text[m.end():]
    return text


def is_auxiliary(variant):
    return variant in ('toolhead', SINGLE_HEATER)


def model_cfg_path(repo, variant, standard, auxiliary=None):
    if is_auxiliary(variant) and auxiliary is not None:
        if variant == SINGLE_HEATER:
            legacy = Path(auxiliary)
            single = repo / (legacy.stem + '_single' + legacy.suffix)
            if single.is_file():
                return single
        common = repo / auxiliary
        if common.is_file():
            return common
    return repo / standard if standard is not None else None


def selected(home):
    value = os.environ.get('LUGOWARE_VARIANT')
    if not value:
        path = home / '.local/share/lugoware/variant.json'
        value = json.loads(path.read_text())['variant'] if path.exists() else 'standard'
        if value == 'toolhead':
            config = home / 'printer_data/config'
            base = config / 'printer_base.cfg'
            auxiliary = config / 'toolhead_auxiliary.cfg'
            if base.is_file() and auxiliary.is_file():
                if (heater_pin(base.read_text(encoding='utf-8-sig'), 'extruder') == 'PC5'
                        and heater_pin(auxiliary.read_text(encoding='utf-8-sig')) == 'PA7'):
                    value = SINGLE_HEATER
    if value not in VARIANTS:
        raise ValueError('Unknown hardware variant; refusing to guess')
    return value


def section(text, name):
    return re.search(r'(?ms)^\[' + re.escape(name) + r'\][^\n]*\n.*?(?=^\[|^#\*#|\Z)', text)


def remove_section(text, name):
    match = section(text, name)
    return text[:match.start()] + text[match.end():] if match else text


def migrate_auxiliary_section(text):
    legacy = section(text, LEGACY_AUX_SENSOR)
    if not legacy:
        return text
    if section(text, AUX[0]):
        return remove_section(text, LEGACY_AUX_SENSOR)
    return (text[:legacy.start()] + legacy[0].replace(
        '[' + LEGACY_AUX_SENSOR + ']', '[' + AUX[0] + ']', 1) + text[legacy.end():])


def nozzle_sensor_profile(text, variant):
    """Use stock PT1000 only in auxiliary mode; preserve PID and return choice."""
    match = section(text, 'extruder')
    if not match:
        return text
    block = match[0]
    marker = '# lugoware_standard_sensor_type: '
    saved = re.search(r'(?m)^' + re.escape(marker) + r'(.+)$', block)
    current = re.search(r'(?m)^sensor_type:[^\n]*$', block)
    if variant == 'toolhead' and current:
        if not saved:
            block = block.replace(current[0], marker + json.dumps(current[0]) + '\n' + current[0], 1)
        block = re.sub(r'(?m)^sensor_type:[^\n]*$', 'sensor_type: PT1000', block)
    elif variant == 'standard' and saved:
        original = json.loads(saved[1])
        if not isinstance(original, str) or '\n' in original or not original.startswith('sensor_type:'):
            raise ValueError('Invalid saved nozzle sensor type')
        block = re.sub(r'(?m)^sensor_type:[^\n]*$', lambda m: original, block)
        block = re.sub(r'(?m)^' + re.escape(marker) + r'.*\n', '', block)
    return text[:match.start()] + block + text[match.end():]


def pid_profile(text, name, values, variant='toolhead', fill=True, remember=False):
    match = section(text, name)
    if not match:
        return text
    block = match[0]
    marker = '# lugoware_standard_pid: '
    saved = re.search(r'(?m)^' + re.escape(marker) + r'(.+)$', block)
    patterns = {k: r'(?m)^' + k + r'\s*[:=][^\n]*\n?' for k in values}
    if variant == 'standard':
        if not saved:
            return text
        original = json.loads(saved[1])
        for key, pattern in patterns.items():
            value = original.get(key, '')
            if value and not re.fullmatch(pattern.replace('(?m)', ''), value):
                raise ValueError('Invalid saved standard PID')
            block = re.sub(pattern, lambda m: value, block)
        block = re.sub(r'(?m)^' + re.escape(marker) + r'.*\n', '', block)
    else:
        original = {k: (re.search(p, block)[0] if re.search(p, block) else '') for k, p in patterns.items()}
        if remember and not saved and (fill or any(original.values())):
            line = block.index('\n') + 1
            block = block[:line] + marker + json.dumps(original) + '\n' + block[line:]
        for key, pattern in patterns.items():
            value = key + ': ' + values[key] + '\n'
            if re.search(pattern, block):
                block = re.sub(pattern, lambda m: value, block)
            elif fill:
                line = block.index('\n') + 1
                block = block[:line] + value + block[line:]
    return text[:match.start()] + block + text[match.end():]


def header_fields(text, variant, nozzle_pid, toolhead_pid):
    text = nozzle_sensor_profile(text, variant)
    text = pid_profile(text, 'extruder', nozzle_pid, variant, fill=False, remember=True)
    if variant == 'toolhead':
        text = pid_profile(text, 'heater_generic Toolhead', toolhead_pid, fill=False)
    return text


def nozzle_header_profile(text, variant, nozzle_pid=NOZZLE_PID, toolhead_pid=TOOLHEAD_PID):
    text = header_fields(text, variant, nozzle_pid, toolhead_pid)
    # SAVE_CONFIG values override ordinary sections; apply the same release PID.
    start = re.search(r'(?m)^#\*# \[', text)
    if start:
        tail = text[start.start():]
        plain = re.sub(r'(?m)^#\*# ?', '', tail)
        patched = header_fields(plain, variant, nozzle_pid, toolhead_pid)
        if patched != plain:
            text = text[:start.start()] + ''.join('#*# ' + line for line in patched.splitlines(True))
    return text


def base_profile(text, variant):
    text = nozzle_sensor_profile(text, variant)
    text = pid_profile(text, 'extruder', NOZZLE_PID, variant, remember=True)
    # Remove only our exact command hooks, never motion or model coordinates.
    text = re.sub(r'(?m)^\s*TOOLHEAD_(?:DOCK_HEAT TEMP=\{normal_temp\}|PARK_OFF)\s*\n', '', text)
    sensor = section(text, SENSOR)
    if variant == 'standard':
        if sensor:
            block = sensor[0].replace('[' + SENSOR + ']', '[filament_switch_sensor toolhead_sensor]')
            block = block.replace('[filament_switch_sensor toolhead_sensor]\n',
                                  '[filament_switch_sensor toolhead_sensor]\nswitch_pin: ^PC3\ndebounce_delay: 0.2\n')
            text = text[:sensor.start()] + block + text[sensor.end():]
        return text
    if not sensor:
        sensor = section(text, 'filament_switch_sensor toolhead_sensor')
        if not sensor:
            raise ValueError('Missing standard toolhead presence sensor')
        block = sensor[0].replace('[filament_switch_sensor toolhead_sensor]', '[' + SENSOR + ']')
        block = re.sub(r'(?m)^\s*(?:switch_pin|debounce_delay):[^\n]*\n', '', block)
        text = text[:sensor.start()] + block + text[sensor.end():]
    extruder = section(text, 'extruder')
    if not extruder or not re.search(r'(?m)^sensor_pin:\s*PA[12]\s*(?:#.*)?$', extruder[0]):
        raise ValueError('Unknown nozzle wiring; verify PA1 before selecting auxiliary profile')
    block = re.sub(r'(?m)^(sensor_pin:\s*)PA2\b', r'\g<1>PA1', extruder[0])
    text = text[:extruder.start()] + block + text[extruder.end():]
    # Pins must be free in the standard model config, apart from our own section.
    for match in re.finditer(r'(?m)^\s*\w*pin\s*[:=]\s*([^#\n]+)', text):
        if re.search(r'(?<![\w])(?:PA2|PB7)(?![\w])', match[1]):
            raise ValueError('PA2/PB7 already assigned in printer_base.cfg')
    for n in range(4):
        name = 'gcode_macro DOCK_TOOL_' + str(n)
        block = section(text, name)
        anchor = '    FAST_CANCEL_WAIT P={(h_d * 1000)|int}'
        if not block or block[0].count(anchor) != 1:
            raise ValueError('Unsupported docking macro: ' + name)
        patched = block[0].replace(anchor, '    TOOLHEAD_DOCK_HEAT TEMP={normal_temp}\n' + anchor)
        text = text[:block.start()] + patched + text[block.end():]
    for name in ['PARK_TOOL_' + str(n) for n in range(4)] + ['PARK_' + str(n) for n in range(4)]:
        text, count = re.subn(r'(?m)^(\[gcode_macro ' + name + r'\]\ngcode:\n)',
                              r'\1    TOOLHEAD_PARK_OFF\n', text)
        if count != 1:
            raise ValueError('Unsupported parking macro: ' + name)
    return text


def patch_ui(text, edits, variant):
    # Existing experimental installations used both Python quote styles.
    # Normalize only this known, semantically identical gettext expression.
    text = text.replace('_("Not attached")', "_('Not attached')")
    for label in ('"미부착"', "'미부착'"):
        old = label + ' if dev == "heater_generic Toolhead" and temp is None'
        text = text.replace(old, "_('Not attached')" + ' if dev == "heater_generic Toolhead" and temp is None')
    # Remove the exact display hooks from the retired experimental nozzle offset.
    text = text.replace(
        '    def nozzle_display_temperature(self, device):\n'
        '        if device != "extruder":\n'
        '            return None\n'
        '        target = self._printer.get_stat(device, "target")\n'
        '        physical = self._printer.get_stat(device, "physical_target")\n'
        '        corrected = self._printer.get_stat(device, "compensated_temperature")\n'
        '        if all(isinstance(v, (float, int)) for v in (target, physical, corrected)) and physical > target > 0:\n'
        '            return corrected\n'
        '        return None\n\n', '')
    text = text.replace('        corrected = self.nozzle_display_temperature(dev)\n'
                        '        if corrected is not None:\n'
                        '            temp = corrected\n', '')
    text = text.replace('                corrected = self.nozzle_display_temperature(device)\n'
                        '                value = f"{(temp if corrected is None else corrected):.0f}°" if valid else "-"\n',
                        '                value = f"{temp:.0f}°" if valid else "-"\n')
    for index, edit in enumerate(edits if variant == 'toolhead' else reversed(edits), 1):
        before, after = edit
        source, target = (before, after) if variant == 'toolhead' else (after, before)
        if source in text:
            if text.count(source) != 1:
                raise ValueError('Ambiguous UI patch anchor')
            text = text.replace(source, target, 1)
        elif target not in text:
            raise ValueError('Unsupported UI revision at patch %d; preserved without modification' % index)
    return text


def dock_wait_profile(text, patches, variant):
    for name, edits in patches.items():
        match = section(text, 'gcode_macro ' + name)
        if not match:
            raise ValueError('Missing tool-change macro: ' + name)
        block = match[0]
        for _, updated in edits:
            # Normalize older auxiliary macros before applying or reverting the profile.
            if name.startswith('PARK_TOOL_'):
                for legacy_offset in ('5', '25', '40', 'printer.' + LEGACY_AUX_SENSOR + '.park_nozzle_preheat_offset'):
                    legacy = updated.replace('printer.toolhead_auxiliary.park_nozzle_preheat_offset',
                                             legacy_offset)
                    if legacy != updated:
                        block = block.replace(legacy, updated)
            elif name.startswith('DOCK_TOOL_'):
                legacy = updated.replace('TOOLHEAD_WAIT_FOR_PRIME TARGET={slicer_temp}\n',
                                         'TOOLHEAD_WAIT_FOR_PRIME TARGET={slicer_temp} TIMEOUT=60\n')
                if legacy != updated:
                    block = block.replace(legacy, updated)
        try:
            changed = patch_ui(block, edits, variant)
        except ValueError as exc:
            raise ValueError('Unsupported tool-change macro ' + name + ': ' + str(exc)) from exc
        text = text[:match.start()] + changed + text[match.end():]
    return text


def apply_release_tuning(content, defaults):
    installed = section(content, AUX[0])
    release = section(defaults, AUX[0])
    if not installed or not release:
        raise ValueError('Missing toolhead sensor section')
    block = installed[0]
    block = re.sub(r'(?mi)^[ \t]*(?:' + '|'.join(LEGACY_NOZZLE_OFFSETS) + r')[ \t]*[:=][^\n]*(?:\n|$)', '', block)
    options = []
    for option in ('sensor_pin', 'pullup_resistor', 'sync_manual_preheat', *TOOLHEAD_TUNING):
        pattern = re.compile(r'(?mi)^[ \t]*' + option +
                             r'[ \t]*[:=][ \t]*([^\n]*?)([ \t]+[#;][^\n]*)?[ \t]*(?:\n|$)')
        defaults_for_option = pattern.findall(release[0])
        if len(defaults_for_option) != 1:
            raise ValueError('Expected one release setting for ' + option)
        value, comment = defaults_for_option[0]
        existing = pattern.findall(block)
        if existing and option not in TOOLHEAD_TUNING:
            value = existing[-1][0]
        options.append(option + ': ' + value + comment + '\n')
        block = pattern.sub('', block)
    return content[:installed.start()] + block.rstrip() + '\n' + ''.join(options) + '\n' + content[installed.end():]


HEADER_GROUP = (
    'include mainsail.cfg', 'include timelapse.cfg', 'include printer_base.cfg',
    'include printer_custom.cfg', 'lugo_tool_temperature', 'fast_cancel', 'print_sensor',
    'exclude_tool_guard', 'include toolhead_auxiliary.cfg', 'lugo_recovery', 'lugo_preanalysis',
)
HEADER_ORDER = HEADER_GROUP + ('probe_auto_recovery', 'mcu CB2', 'mcu', 'virtual_sdcard',
                               'screen_mesh', 'lugo_diagnostics')
HEADER_SECTION = re.compile(r'(?m)^\[([^\]\r\n]+)\][^\r\n]*(?:\r?\n|$)')
AUXILIARY_INCLUDE = 'include toolhead_auxiliary.cfg'


def header_layout(base, variant, template):
    match = re.search(r'(?m)^#\s*FLEX4_([MLW])_V\d', base[:8192])
    model = match[1] if match else None
    if template is None:
        return HEADER_ORDER, model
    expected = tuple(name for name in HEADER_ORDER if variant == 'toolhead' or name != AUXILIARY_INCLUDE)
    actual = tuple(m[1] for m in HEADER_SECTION.finditer(template))
    diagnostics = section(template, 'lugo_diagnostics')
    selected_model = re.search(r'(?m)^model:\s*([MLW])\s*$', diagnostics[0]) if diagnostics else None
    if (len(actual) != len(expected) or set(actual) != set(expected)
            or tuple(name for name in actual if name in HEADER_GROUP) != tuple(name for name in expected if name in HEADER_GROUP)
            or model is not None and (selected_model is None or selected_model[1] != model)):
        raise ValueError('Released printer.cfg layout does not match the selected model and variant')
    return actual, model


def organize_printer_header(text, order=HEADER_ORDER, model=None):
    marker = '#*# <---------------------- SAVE_CONFIG ---------------------->'
    body, separator, saved = text.partition(marker)
    matches = list(HEADER_SECTION.finditer(body))
    names = [match[1] for match in matches]
    # Leave custom includes in their original precedence and do not merge repeated sections.
    if any(name.startswith('include ') and name not in HEADER_GROUP for name in names):
        return text
    managed = [name for name in names if name in order]
    if not managed or len(managed) != len(set(managed)):
        return text
    eol = '\r\n' if '\r\n' in body else '\n'
    blocks = {}
    remaining = []
    cursor = 0
    for index, match in enumerate(matches):
        name = match[1]
        if name not in order:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        lines = body[match.start():end].splitlines(keepends=True)
        while len(lines) > 1 and (not lines[-1].strip() or lines[-1].lstrip().startswith(('#', ';'))):
            lines.pop()
        block = ''.join(lines).rstrip('\r\n')
        if name == 'lugo_diagnostics' and model is not None:
            block, count = re.subn(r'(?m)^([ \t]*model[ \t]*[:=][ \t]*)[^\r\n]*',
                                   lambda found: found[1] + model, block, count=1)
            if not count:
                block += eol + 'model: ' + model
        blocks[name] = block
        remaining.append(body[cursor:match.start()])
        cursor = match.start() + sum(map(len, lines))
    remaining.append(body[cursor:])
    rest = ''.join(remaining)
    first = HEADER_SECTION.search(rest)
    intro, extra = (rest[:first.start()], rest[first.start():]) if first else (rest, '')
    parts = [intro.strip('\r\n')] if intro.strip() else []
    group = [blocks[name] for name in order if name in HEADER_GROUP and name in blocks]
    if group:
        parts.append(eol.join(group))
    parts.extend(blocks[name] for name in order if name not in HEADER_GROUP and name in blocks)
    if extra.strip():
        parts.append(extra.rstrip('\r\n'))
    return (eol * 2).join(parts) + (eol * 2 if separator else eol) + separator + saved


def toolchange_profile(base, variant, assets):
    dock_patches = json.loads((assets / 'dock_wait_patches.json').read_text(encoding='utf-8'))
    if ('TOOLHEAD_WAIT_FOR_PRIME TARGET={slicer_temp}' in base
            or '.park_nozzle_preheat_offset' in base):
        base = dock_temperature_actions(remove_dock_retry(base), False)
        base = dock_wait_profile(base, dock_patches, 'standard')
    base = base_profile(base, variant)
    if variant == 'standard':
        return add_dock_retry(base, assets)
    base = dock_temperature_actions(dock_wait_profile(base, dock_patches, 'toolhead'), True)
    resume = section(base, 'gcode_macro RESUME')
    if not resume:
        raise ValueError('Missing RESUME macro for auxiliary dock safety')
    pattern = r'(?m)^([ \t]*)' + re.escape(RESUME_PAUSED) + r'$'
    guarded, count = re.subn(pattern, lambda m: '\n'.join(
        m[1] + line for line in (RESUME_DOCK_HOLD,
                                 *('  ' + line for line in RESUME_DOCK_CONFIRM),
                                 RESUME_PAUSED.replace(' if ', ' elif '))), resume[0])
    if count != 1:
        raise ValueError('Unsupported RESUME macro for auxiliary dock safety')
    return add_dock_retry(base[:resume.start()] + guarded + base[resume.end():], assets)


PAUSE_RETURN = 'gcode_macro _PAUSE_RETURN_XY'
PAUSE_RETURN_CALL = '_PAUSE_RETURN_XY'
CANCEL_RETURN_CHECK = '_PAUSE_RETURN_XY PARK_SLOT={tool} CANCEL_CHECK=1'


def pause_return_profile(base, enable):
    # Undo our hooks before reapplying them, including the initial on-device patch.
    if section(base, PAUSE_RETURN):
        base = remove_section(base, PAUSE_RETURN)
        base = re.sub(r'(?m)^([ \t]+)_PAUSE_RETURN_XY(?: PARK_SLOT=[0-3])?[ \t]*$',
                      r'\1G1 X0 F40000', base)
        base = re.sub(r'(?m)^([ \t]+)_PAUSE_RETURN_XY EMPTY_PATH=1[ \t]*$',
                      r'\1G1 X0 F40000\n\1SET_GCODE_VARIABLE MACRO=TOOL_STATE VARIABLE=active_tool VALUE=-1', base)
        base = re.sub(r'(?m)^[ \t]+' + re.escape(CANCEL_RETURN_CHECK) + r'[ \t]*\n', '', base)
    if not enable:
        return base

    exits = []
    edits = {}
    for slot in range(4):
        park = section(base, 'gcode_macro PARK_TOOL_%d' % slot)
        route = section(base, 'gcode_macro _TOOL_RETRY_PARK_XY_T%d' % (slot + 1))
        exit_pattern = (r'(?m)^    G1 Y([0-9.]+) F[^\n]+\n    G1 X\S+ F[^\n]+\n'
                        r'    G1 X([0-9.]+) F[^\n]+\n    M400[ \t]*$')
        park_exit = re.search(exit_pattern, park[0]) if park else None
        route_exit = re.search(exit_pattern, route[0]) if route else None
        if (not park_exit or not route_exit or park_exit.groups() != route_exit.groups()
                or 'FAST_CANCEL_PHASE PHASE=empty TOOL=%d' % slot not in park[0]):
            exits = []
            break
        exits.append((float(park_exit[2]), float(park_exit[1])))

    for action in ('T0', 'T1', 'T2', 'T3', 'A1'):
        name = 'gcode_macro PAUSE_ACTION_' + action
        match = section(base, name)
        pattern = r'(?m)^([ \t]+)G1 X0 F40000[ \t]*$'
        args = ' PARK_SLOT=' + action[1] if action.startswith('T') else ' EMPTY_PATH=1'
        if action == 'A1':
            pattern += r'\n[ \t]+SET_GCODE_VARIABLE MACRO=TOOL_STATE VARIABLE=active_tool VALUE=-1[ \t]*$'
        if not match:
            return base
        changed, count = re.subn(pattern, lambda m: m[1] + PAUSE_RETURN_CALL + args, match[0])
        if count != 1:
            return base
        edits[name] = changed

    cancel_name = 'gcode_macro _FAST_CANCEL_MOTION'
    cancel = section(base, cancel_name)
    if exits and cancel:
        pattern = r'(?m)^(([ \t]+)PARK_TOOL_\{tool\}[^\n]*\n[ \t]+M400[ \t]*\n)(?=[ \t]+\{% endif %\})'
        changed, count = re.subn(pattern, lambda m: m[1] + m[2] + CANCEL_RETURN_CHECK + '\n', cancel[0])
        if count == 1:
            edits[cancel_name] = changed

    for name, body in edits.items():
        match = section(base, name)
        base = base[:match.start()] + body + base[match.end():]
    return base.rstrip() + '\n\n' + pause_return_macro(exits)


def pause_return_macro(exits):
    return """[gcode_macro _PAUSE_RETURN_XY]
gcode:
    {% set sensor = printer['filament_switch_sensor toolhead_sensor'] %}
    {% set tool = printer['gcode_macro TOOL_STATE'] %}
    {% set head = printer.toolhead %}
    {% set origin = printer.gcode_move.homing_origin %}
    {% set empty_path = params.EMPTY_PATH|default(0)|int %}
    {% set slot = params.PARK_SLOT|default(-1)|int %}
    {% set cancel_check = params.CANCEL_CHECK|default(0)|int %}
    {% set uncertain = sensor.filament_detected or (sensor.source|default('') == 'PA2 thermistor' and sensor.state != 'disconnected') %}
    {% set x_in_range = head.axis_minimum.x <= 10 + origin.x <= head.axis_maximum.x %}
    {% set y_in_range = head.axis_minimum.y <= 125 + origin.y <= head.axis_maximum.y %}
    {% set exits = PARK_EXIT_COORDINATES %}
    {% set at_park_exit = slot >= 0 and slot < exits|length and printer.fast_cancel.phase == 'empty' and printer.fast_cancel.tool == slot and tool.is_parked|int and (head.position.x - exits[slot][0])|abs < 0.1 and (head.position.y - exits[slot][1])|abs < 0.1 and origin.x|abs < 0.1 and origin.y|abs < 0.1 %}
    {% if 'x' not in head.homed_axes or 'y' not in head.homed_axes or 'z' not in head.homed_axes or not x_in_range %}
        {action_respond_info("Return skipped: position or X10 clearance could not be verified.")}
    {% elif uncertain and at_park_exit %}
        G90
        G1 X10 F3600
        M400
        RESPOND MSG="Moved to X10 only. Inspect the toolhead attachment."
    {% elif cancel_check %}
        # Normal cancel still verifies detachment before moving Y.
    {% elif printer.fast_cancel.phase not in ['normal', 'empty'] or uncertain or (empty_path and tool.active_tool|int in [0, 1, 2, 3] and not tool.is_parked|int) %}
        {action_respond_info("Pause return skipped: inspect the toolhead attachment.")}
    {% elif not y_in_range %}
        {action_respond_info("Pause return skipped: Y125 is outside axis limits.")}
    {% else %}
        G90
        G1 X10 F40000
        G1 Y125 F20000
        M400
        {% if empty_path %}
            SET_GCODE_VARIABLE MACRO=TOOL_STATE VARIABLE=active_tool VALUE=-1
        {% endif %}
    {% endif %}
""".replace('PARK_EXIT_COORDINATES', repr(exits))


def plan_paused_tools(home, assets, base, variant, screen_override, changes):
    config = home / 'printer_data/config'
    available = all(section(base, 'gcode_macro _TOOL_RETRY_%s_XY_T%d' % (action, slot))
                    for slot in range(1, 5) for action in ('DOCK', 'PARK'))
    if not available and not paused_tools.installed(home):
        return base
    if available:
        base = paused_tools.configure(base, variant == 'toolhead')
        runtime = assets.parent.parent / 'panels' / 'runtime'
        for rel in TOOL_CARD_RUNTIME:
            changes[home / 'KlipperScreen' / rel] = runtime_payload(runtime / rel)
        for rel, name in paused_tools.FILES.items():
            data = (assets.parent / 'paused_tool_service' / name).read_bytes()
            ast.parse(data)
            changes[home / rel] = data
    screen_path = config / 'KlipperScreen.conf'
    screen = screen_override if screen_override is not None else screen_path.read_text(encoding='utf-8')
    changes[screen_path] = paused_tools.menu(screen, available).encode()
    for rel in paused_tools.HOOKS:
        path = home / rel
        old = changes[path].decode() if path in changes else path.read_text(encoding='utf-8')
        new = paused_tools.hooks(old, rel, available)
        ast.parse(new)
        changes[path] = new.encode()
    return base


def option_profile(text, name, option, value, required=True):
    block = section(text, name)
    pattern = r'(?m)^([ \t]*' + re.escape(option) + r'[ \t]*[:=][ \t]*)[^#;\r\n]+'
    if block:
        updated, count = re.subn(pattern, lambda m: m[1] + value + re.search(r'[ \t]*$', m[0])[0], block[0])
        if count == 1:
            return text[:block.start()] + updated + text[block.end():]
        if count > 1:
            raise ValueError('Duplicate option: ' + name + ' / ' + option)
    if required:
        raise ValueError('Missing option: ' + name + ' / ' + option)
    return text


AUX_FAN_SAVE = '    {% set part_fan_pwm = (printer.fan.speed|float * 255)|round(0)|int %}\n    M107\n'
AUX_FAN_RESTORE = '    _RESTORE_TOOLCHANGE_PART_FAN TOOL={next_tool} PWM={part_fan_pwm}\n'
AUX_FAN_MACRO = '''[gcode_macro _RESTORE_TOOLCHANGE_PART_FAN]
gcode:
    {% set tc = printer.fast_cancel %}
    {% set tool = params.TOOL|int %}
    {% set pwm = params.PWM|int %}
    {% if 0 < pwm <= 255 and tc.phase == 'docked' and tc.tool == tool and not tc.requested and not tc.cleaning and printer['gcode_macro TOOL_STATE'].active_tool|int == tool %}
        M106 S{pwm}
    {% endif %}'''
DUTY_CHECK = '{% if target > 0 and duty > 0.85 and rise < 5.0 %}'
AUX_DUTY_CHECK = DUTY_CHECK.replace('and duty', 'and (target - temp) > 5.0 and duty')


def auxiliary_print_profile(base, enabled):
    verifier = section(base, 'verify_heater extruder')
    if verifier:
        backup = re.search(r'(?m)^# lugoware_standard_max_error: ([0-9.eE+-]+)\n', verifier[0])
        if enabled and not backup:
            value = re.search(r'(?m)^max_error[ \t]*[:=][ \t]*([0-9.eE+-]+)', verifier[0])
            if not value:
                raise ValueError('Missing nozzle max_error')
            index = verifier.start() + verifier[0].index('\n') + 1
            base = base[:index] + '# lugoware_standard_max_error: ' + value[1] + '\n' + base[index:]
        if enabled or backup:
            base = option_profile(base, 'verify_heater extruder', 'max_error', '400' if enabled else backup[1])
        if not enabled and backup:
            base = base.replace(backup[0], '', 1)
    elif enabled:
        raise ValueError('Missing nozzle heater verification')

    base = remove_section(base, 'gcode_macro _RESTORE_TOOLCHANGE_PART_FAN')
    duty = section(base, 'delayed_gcode duty_guard_check')
    if duty:
        block = duty[0].replace(AUX_DUTY_CHECK, DUTY_CHECK)
        if enabled:
            if block.count(DUTY_CHECK) != 1:
                raise ValueError('Unsupported nozzle duty guard')
            block = block.replace(DUTY_CHECK, AUX_DUTY_CHECK)
        base = base[:duty.start()] + block + base[duty.end():]
    change = section(base, 'gcode_macro CHANGE_TOOL')
    if enabled and (not change or not duty):
        raise ValueError('Missing toolchange or nozzle duty guard')
    if change:
        block = change[0].replace(AUX_FAN_SAVE, '').replace(AUX_FAN_RESTORE, '')
        if enabled:
            start = '    {% if st.active_tool|int != next_tool %}\n'
            end = r'(?m)^    M220 S\{\(sf \* 100\)\|round\(1\)\}[^\n]*\n'
            if block.count(start) != 1:
                raise ValueError('Unsupported toolchange fan start')
            block = block.replace(start, start + AUX_FAN_SAVE)
            block, count = re.subn(end, lambda m: m[0] + AUX_FAN_RESTORE, block)
            if count != 1:
                raise ValueError('Unsupported toolchange fan restore point')
            block = block.rstrip() + '\n\n' + AUX_FAN_MACRO + '\n\n'
        base = base[:change.start()] + block + base[change.end():]
    return base


def heater_pin(content, name=AUX[1]):
    heater = section(content, name)
    if not heater:
        return None
    found = re.search(r'(?m)^[ \t]*heater_pin[ \t]*[:=][ \t]*([^\s#;]+)', heater[0])
    return found[1] if found else None


def single_heater_base(base):
    base = option_profile(base, 'extruder', 'heater_pin', 'PC5')
    base = remove_section(base, 'multi_pin dual_hotend_heater')
    base = re.sub(r'(?m)^[ \t]*SET_MULTI_PIN_MODE[ \t]+PIN=dual_hotend_heater[^\r\n]*\r?\n', '', base)
    for match in re.finditer(r'(?m)^[ \t]*\w*pins?[ \t]*[:=][ \t]*([^#;\n]+)', base):
        if re.search(r'\bPA7\b', match[1]):
            raise ValueError('PA7 already assigned in printer_base.cfg')
    return pid_profile(base, 'extruder', SINGLE_NOZZLE_PID)


def merge_auxiliary_release(content, defaults):
    # Start with the installed file so device-specific options and sections survive.
    defaults = migrate_auxiliary_section(defaults.rstrip() + '\n')
    content = migrate_auxiliary_section(content) if content is not None else defaults
    content = apply_release_tuning(content, defaults)
    heater = section(defaults, AUX[1])
    if not heater or not section(content, AUX[1]):
        raise ValueError('Missing auxiliary heater section')
    config = configparser.RawConfigParser(inline_comment_prefixes=('#', ';'))
    config.read_string(heater[0])
    pid = {name: config.get(AUX[1], name) for name in TOOLHEAD_PID}
    if pid['control'] != 'pid':
        raise ValueError('Released auxiliary heater must use PID control')
    verifier = 'verify_heater Toolhead'
    max_error = '400'
    block = section(content, verifier)
    if block is None:
        content = content.rstrip() + f'\n\n[{verifier}]\nmax_error: {max_error}\n'
    elif re.search(r'(?m)^[ \t]*max_error[ \t]*[:=]', block[0]):
        content = option_profile(content, verifier, 'max_error', max_error)
    else:
        line = content.index('\n', block.start()) + 1
        content = content[:line] + f'max_error: {max_error}\n' + content[line:]
    for name in ('gcode_macro TOOLHEAD_IDLE_STATE', 'delayed_gcode turn_off_toolhead'):
        macro = section(defaults, name)
        if not macro:
            raise ValueError('Missing auxiliary heater macro: ' + name)
        content = remove_section(content, name).rstrip() + '\n\n' + macro[0]
    return pid_profile(content, AUX[1], pid)


def plan(home, variant, assets, base_override=None, screen_override=None, auxiliary_override=None,
         header_template=None, single_auxiliary_override=False):
    if variant not in VARIANTS:
        raise ValueError('Invalid variant')
    profile = variant
    single = profile == SINGLE_HEATER
    if is_auxiliary(profile):
        variant = 'toolhead'
    nozzle_pid = SINGLE_NOZZLE_PID if single else NOZZLE_PID
    toolhead_pid = SINGLE_TOOLHEAD_PID if single else TOOLHEAD_PID
    config = home / 'printer_data/config'
    header_path = config / 'printer.cfg'
    original_header = header_path.read_bytes().decode('utf-8')
    header = migrate_auxiliary_section(original_header)
    base_path = config / 'printer_base.cfg'
    base = base_override if base_override is not None else base_path.read_text(encoding='utf-8')
    order, model = header_layout(base, variant, header_template)
    marker = home / '.local/share/lugoware/variant.json'
    previous = json.loads(marker.read_text())['variant'] if marker.exists() else None
    experimental = bool(section(header, AUX[0]) or section(base, SENSOR)
                        or '[include toolhead_auxiliary.cfg]' in header)
    changes = {}
    if variant == 'standard' and not is_auxiliary(previous) and not experimental:
        organized = organize_printer_header(header, order, model)
        if organized != original_header:
            changes[header_path] = organized.encode()
        changes[marker] = json.dumps({'variant': variant}).encode()
        new = add_dock_retry(paused_tools.strip_config(prepare_extrusion_distance(base)), assets)
        new = pause_return_profile(new, False)
        new = plan_paused_tools(home, assets, new, variant, screen_override, changes)
        if new != base:
            changes[base_path] = new.encode()
        return changes
    auxiliary = config / 'toolhead_auxiliary.cfg'
    if variant == 'toolhead':
        blocks = [section(header, name) for name in AUX]
        if all(blocks):
            content = ''.join(match[0] for match in blocks)
        elif auxiliary.exists():
            content = auxiliary.read_text(encoding='utf-8-sig')
        else:
            content = None
        defaults = auxiliary_override
        if defaults is None:
            defaults = (assets / 'toolhead_auxiliary.cfg').read_text(encoding='utf-8')
        merged = merge_auxiliary_release(content, defaults)
        if single:
            merged = option_profile(merged, AUX[1], 'heater_pin', 'PA7')
            if not single_auxiliary_override:
                merged = option_profile(merged, AUX[0], 'prime_temperature_margin', '0')
                merged = pid_profile(merged, AUX[1], toolhead_pid)
        elif previous == SINGLE_HEATER:
            merged = option_profile(merged, AUX[1], 'heater_pin', 'PB7')
        elif (heater_pin(merged) or '').lstrip('!^~') in ('PC5', 'PA7'):
            raise ValueError('Auxiliary heater pin conflicts with the dual nozzle. Select the matching heater profile.')
        changes[auxiliary] = merged.encode()
    for name in AUX:
        header = remove_section(header, name)
    if variant == 'standard':
        # SAVE_CONFIG may have written heater PID into the generated trailer.
        header = re.sub(r'(?ms)^#\*# \[heater_generic Toolhead\]\n.*?(?=^#\*# \[|\Z)', '', header)
    header = re.sub(r'(?m)^\[include toolhead_auxiliary.cfg\]\s*\n', '', header)
    if variant == 'toolhead':
        header = '[include toolhead_auxiliary.cfg]\n' + header
    if single:
        header = option_profile(header, 'extruder', 'heater_pin', 'PC5', required=False)
    elif previous == SINGLE_HEATER:
        if not section(base, 'multi_pin dual_hotend_heater'):
            raise ValueError('The selected profile needs the original model config; run the installer.')
        header = option_profile(header, 'extruder', 'heater_pin', 'multi_pin:dual_hotend_heater', required=False)
    changes[header_path] = organize_printer_header(
        nozzle_header_profile(header, variant, nozzle_pid, toolhead_pid), order, model).encode()
    base = toolchange_profile(paused_tools.strip_config(prepare_extrusion_distance(base)), variant, assets)
    if single:
        base = single_heater_base(base)
    if variant == 'toolhead' or is_auxiliary(previous):
        base = auxiliary_print_profile(base, variant == 'toolhead')
    base = pause_return_profile(base, variant == 'toolhead')
    patches = json.loads((assets / 'ui_patches.json').read_text(encoding='utf-8'))
    for rel, edits in patches.items():
        path = home / rel
        old = path.read_text(encoding='utf-8')
        if rel == 'KlipperScreen/panels/tool_prepare.py' and 'from ks_includes.lugo_tool_cards import ' in old:
            continue  # Shared panel already queries current state before preparation motions.
        try:
            new = patch_ui(old, edits, variant)
        except ValueError as exc:
            raise ValueError('%s: %s' % (rel, exc)) from exc
        ast.parse(new)
        changes[path] = new.encode()
    changes[base_path] = plan_paused_tools(home, assets, base, variant, screen_override, changes).encode()
    if variant == 'toolhead':
        for name in TOOLHEAD_MODULES:
            data = (assets / name).read_bytes()
            ast.parse(data)
            changes[home / 'klipper/klippy/extras' / name] = data
        for lang, value in json.loads((assets / 'translations.json').read_text(encoding='utf-8')).items():
            path = home / 'KlipperScreen/ks_includes/screen_locales' / (lang + '.json')
            catalog = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            catalog['Not attached'] = value
            changes[path] = json.dumps(catalog, ensure_ascii=False, indent=2).encode()
    index = home / 'mainsail/index.html'
    text = index.read_text(encoding='utf-8')
    text = re.sub(r'<script\b[^>]*\bsrc=["\'][^"\']*lugoware-toolhead-temperature\.js[^"\']*["\'][^>]*>\s*</script>', '', text)
    if variant == 'toolhead':
        if '</body>' not in text:
            raise ValueError('Unsupported Mainsail index')
        text = text.replace('</body>', '<script defer src="./lugoware-toolhead-temperature.js?v=1.2.58"></script></body>')
        source = (assets / 'lugoware-toolhead-temperature.js').read_bytes()
        catalog = json.loads((assets / 'notice_locales.json').read_text(encoding='utf-8'))
        changes[home / 'mainsail/lugoware-toolhead-temperature.js'] = source.replace(
            b'/* LUGOWARE_NOTICE_DATA */ null', json.dumps(catalog, ensure_ascii=True).encode())
    changes[index] = text.encode()
    # Unused module files/auxiliary cfg remain for rollback, but no config loads
    # them in standard mode. The Mainsail script is likewise not included.
    changes[marker] = json.dumps({'variant': profile}).encode()
    return changes


def desired_mode(path):
    # Only these public web assets require nginx access. Never relax secrets,
    # printer configs, backups or the company's restrictive process umask.
    if path.parent.name == 'mainsail' and path.name in (
            'index.html', 'lugoware-toolhead-temperature.js'):
        return 0o644
    return stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600


def commit(changes, backup):
    # Do not manufacture file events for already-current config/UI files.
    changes = {p: data for p, data in changes.items()
               if not p.is_file() or p.read_bytes() != data
               or (os.name == 'posix' and stat.S_IMODE(p.stat().st_mode) != desired_mode(p))}
    backup.mkdir(parents=True, exist_ok=False)
    previous = {p: p.read_bytes() if p.exists() else None for p in changes}
    previous_modes = {p: stat.S_IMODE(p.stat().st_mode) if p.exists() else None for p in changes}
    manifest = []
    for i, (path, data) in enumerate(previous.items()):
        manifest.append({'path': str(path), 'backup': str(i) if data is not None else None,
                         'mode': previous_modes[path]})
        if data is not None:
            (backup / str(i)).write_bytes(data)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    touched = []
    try:
        for index, (path, data) in enumerate(changes.items()):
            path.parent.mkdir(parents=True, exist_ok=True)
            # A staging file inside config produces a move_file notification.
            # Mainsail's move handler appends it even if the destination exists.
            # Stage in our unwatched backup directory: rename remains atomic,
            # while Moonraker emits create_file (Mainsail's idempotent upsert).
            if path.parent.stat().st_dev != backup.stat().st_dev:
                raise ValueError('Variant backup and destination must share a filesystem')
            tmp = backup / ('.variant-stage-' + str(index))
            tmp.write_bytes(data)
            tmp.chmod(desired_mode(path))
            os.replace(tmp, path)
            touched.append(path)
    except Exception:
        for path in reversed(touched):
            if previous[path] is None:
                path.unlink()
            else:
                path.write_bytes(previous[path])
                path.chmod(previous_modes[path])
        raise


def apply(home, variant, backup, base_override=None):
    assets = Path(__file__).with_name('toolhead_variant')
    repo = home / 'lugoware_config'
    auxiliary_path = model_cfg_path(repo, variant, None, 'toolhead_auxiliary.cfg')
    auxiliary = auxiliary_path.read_text(encoding='utf-8-sig') if auxiliary_path else None
    template_path = model_cfg_path(repo, variant, None if is_auxiliary(variant) else 'printer_header.cfg',
                                'printer_header_toolhead.cfg')
    template = template_path.read_text(encoding='utf-8-sig') if template_path and template_path.is_file() else None
    changes = plan(home, variant, assets, base_override, auxiliary_override=auxiliary,
                   header_template=template, single_auxiliary_override=(
                       auxiliary_path is not None and auxiliary_path.name == 'toolhead_auxiliary_single.cfg'))
    commit(changes, backup)


def restore(backup):
    """Restore the files and modes saved by a completed commit."""
    entries = json.loads((backup / 'manifest.json').read_text())
    for index, entry in enumerate(reversed(entries)):
        path = Path(entry['path'])
        if entry['backup'] is None:
            path.unlink(missing_ok=True)
            continue
        temporary = backup / ('.variant-restore-' + str(index))
        temporary.write_bytes((backup / entry['backup']).read_bytes())
        temporary.chmod(entry['mode'])
        os.replace(temporary, path)


def preflight(home, variant, assets, screen_upgrade_pending=None):
    """Check package integrity and non-replaced UI before system mutations."""
    patches = json.loads((assets / 'ui_patches.json').read_text(encoding='utf-8'))
    json.loads((assets / 'translations.json').read_text(encoding='utf-8'))
    json.loads((assets / 'dock_retry_paths.json').read_text(encoding='utf-8'))
    for name in TOOLHEAD_MODULES:
        ast.parse((assets / name).read_bytes())
    for name in paused_tools.FILES.values():
        ast.parse((assets.parent / 'paused_tool_service' / name).read_bytes())
    for name in ('toolhead_auxiliary.cfg', 'lugoware-toolhead-temperature.js'):
        if not (assets / name).read_bytes():
            raise ValueError('Empty variant package asset: ' + name)
    marker = home / '.local/share/lugoware/variant.json'
    previous = json.loads(marker.read_text())['variant'] if marker.exists() else None
    if previous is not None and previous not in VARIANTS:
        raise ValueError('Invalid stored hardware profile; inspect variant.json')
    header = migrate_auxiliary_section((home / 'printer_data/config/printer.cfg').read_text(encoding='utf-8'))
    experimental = bool(section(header, AUX[0]) or '[include toolhead_auxiliary.cfg]' in header)
    if variant == 'standard' and not is_auxiliary(previous) and not experimental:
        return
    if variant == 'toolhead' and previous != SINGLE_HEATER:
        auxiliary = home / 'printer_data/config/toolhead_auxiliary.cfg'
        content = auxiliary.read_text(encoding='utf-8-sig') if auxiliary.is_file() else header
        if (heater_pin(content) or '').lstrip('!^~') in ('PC5', 'PA7'):
            raise ValueError('Auxiliary heater pin conflicts with the dual nozzle. Select the matching heater profile.')
    if is_auxiliary(variant):
        variant = 'toolhead'
    if screen_upgrade_pending is None:
        import subprocess
        from upgrade_klipperscreen import MIN_VERSION
        from upgrade_klipper import version_key
        screen = home / 'KlipperScreen'
        version = subprocess.check_output(['git', '-C', str(screen), 'describe', '--tags', '--long', '--dirty'], text=True).strip()
        gitdir = Path(subprocess.check_output(['git', '-C', str(screen), 'rev-parse', '--absolute-git-dir'], text=True).strip())
        screen_upgrade_pending = (version_key(version) < MIN_VERSION or (gitdir/'lugoware-screen-pending').exists())
    if screen_upgrade_pending:
        # Old UI will be replaced by the pinned baseline before final validation.
        print('Variant preflight: pinned screen upgrade will run before UI checks.')
        return
    for rel, edits in patches.items():
        # The common installer supplies these files before applying the variant.
        if rel in ('KlipperScreen/panels/tool_prepare.py', 'klipper/klippy/extras/fast_cancel.py',
                   'klipper/klippy/extras/lugo_tool_temperature.py'):
            continue
        path = home / rel
        if not path.is_file():
            raise ValueError('Missing UI file before installation: ' + rel)
        try:
            ast.parse(patch_ui(path.read_text(encoding='utf-8'), edits, variant))
        except (ValueError, SyntaxError) as exc:
            raise ValueError('Preflight failed for %s: %s; no variant files changed' % (rel, exc)) from exc


def capture(home, backup):
    """Save machine-specific experimental PID before the common header refresh."""
    cfg = home / 'printer_data/config'
    header = migrate_auxiliary_section((cfg / 'printer.cfg').read_text(encoding='utf-8'))
    blocks = [section(header, name) for name in AUX]
    changes = {}
    if all(blocks):
        changes[cfg / 'toolhead_auxiliary.cfg'] = ''.join(m[0] for m in blocks).encode()
        changes[home / '.local/share/lugoware/variant.json'] = json.dumps({'variant': 'toolhead'}).encode()
    if changes:
        commit(changes, backup)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', choices=VARIANTS)
    parser.add_argument('--capture', action='store_true')
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    home = Path.home()
    if args.preflight:
        preflight(home, args.variant or selected(home), Path(__file__).with_name('toolhead_variant'))
        print('M5P variant preflight passed')
        raise SystemExit(0)
    if args.capture:
        capture(home, args.backup)
        raise SystemExit(0)
    apply(home, args.variant or selected(home), args.backup)
    print('M5P variant applied: ' + (args.variant or selected(home)))
