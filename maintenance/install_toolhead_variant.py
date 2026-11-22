"""M5P opt-in auxiliary heater profile. Pure planning before transactional writes."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import paused_tool_service_hooks as paused_tools

VARIANTS = ('standard', 'toolhead')
SENSOR = 'temperature_toolhead_sensor toolhead_sensor'
AUX = ('toolhead_auxiliary', 'heater_generic Toolhead')
LEGACY_AUX_SENSOR = 'toolhead_temperature_test'
TOOLHEAD_MODULES = ('toolhead_auxiliary.py', 'toolhead_temperature_test.py',
                    'temperature_toolhead_sensor.py', 'detachable_heater_sensor.py',
                    'lugo_dock_recovery.py')
NOZZLE_PID = dict(control='pid', pid_kp='13.953', pid_ki='0.511', pid_kd='95.230')
TOOLHEAD_PID = dict(control='pid', pid_kp='37.681', pid_ki='9.191', pid_kd='38.623')
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
    return text


def remove_dock_retry(text):
    text = strip_dock_routes(text)
    alternate = '|'.join(r'\n'.join(r'[ \t]+' + re.escape(l.lstrip()) for l in body)
                         for body in ((RESUME_DOCK_MESSAGE,), RESUME_DOCK_CONFIRM))
    guard = r'(?m)^([ \t]*)' + re.escape(RESUME_DOCK_HOLD) + r'\n(?:' + alternate + ')'
    guard += r'\n[ \t]*' + re.escape(RESUME_PAUSED.replace(' if ', ' elif '))
    return re.sub(guard, lambda m: m[1] + RESUME_PAUSED, text)


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
            block = '[gcode_macro _T%d_RETRY_%s_XY]\n' % (slot, action.upper())
            if action == 'dock':
                x = float(re.findall(r'\bX(-?[\d.]+)', '\n'.join(commands))[-1])
                y = float(re.findall(r'\bY(-?[\d.]+)', '\n'.join(commands))[-1])
                block += ('variable_retry_x: %s\nvariable_retry_y: %s\nvariable_retry_exit: %r\n'
                          % (x, y, (366. + delta, 361. + delta, 334.5 + delta)))
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


def selected(home):
    value = os.environ.get('LUGOWARE_VARIANT')
    if not value:
        path = home / '.local/share/lugoware/variant.json'
        value = json.loads(path.read_text())['variant'] if path.exists() else 'standard'
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


def header_fields(text, variant):
    text = nozzle_sensor_profile(text, variant)
    text = pid_profile(text, 'extruder', NOZZLE_PID, variant, fill=False, remember=True)
    if variant == 'toolhead':
        text = pid_profile(text, 'heater_generic Toolhead', TOOLHEAD_PID, fill=False)
    return text


def nozzle_header_profile(text, variant):
    text = header_fields(text, variant)
    # SAVE_CONFIG values override ordinary sections; apply the same release PID.
    start = re.search(r'(?m)^#\*# \[', text)
    if start:
        tail = text[start.start():]
        plain = re.sub(r'(?m)^#\*# ?', '', tail)
        patched = header_fields(plain, variant)
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


def header_block(text, name):
    match = section(text, name)
    if not match:
        return None
    lines = match[0].splitlines(keepends=True)
    # Keep comments between sections in place, including the top-level heading.
    while len(lines) > 1 and (not lines[-1].strip() or lines[-1].lstrip().startswith(('#', ';'))):
        lines.pop()
    return match.start(), ''.join(lines)


def organize_printer_header(text):
    marker = '#*# <---------------------- SAVE_CONFIG ---------------------->'
    body, separator, saved = text.partition(marker)
    anchor = 'exclude_tool_guard'
    if not section(body, anchor):
        return text
    eol = '\r\n' if '\r\n' in body else '\n'
    grouped = []
    for name in ('include toolhead_auxiliary.cfg', 'lugo_recovery', 'lugo_preanalysis'):
        found = header_block(body, name)
        if found:
            start, block = found
            grouped.append(block.rstrip('\r\n'))
            body = body[:start] + body[start + len(block):].lstrip('\r\n')
    if not grouped:
        return text
    start, block = header_block(body, anchor)
    end = start + len(block)
    header = body[:end].rstrip('\r\n') + eol + eol.join(grouped)
    return header + eol * 2 + body[end:].lstrip('\r\n') + separator + saved


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


def plan_paused_tools(home, assets, base, variant, screen_override, changes):
    config = home / 'printer_data/config'
    available = all(section(base, 'gcode_macro _T%d_RETRY_%s_XY' % (slot, action))
                    for slot in range(1, 5) for action in ('DOCK', 'PARK'))
    if not available and not paused_tools.installed(home):
        return base
    if available:
        base = paused_tools.configure(base, variant == 'toolhead')
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


def plan(home, variant, assets, base_override=None, screen_override=None):
    if variant not in VARIANTS:
        raise ValueError('Invalid variant')
    config = home / 'printer_data/config'
    header_path = config / 'printer.cfg'
    original_header = header_path.read_bytes().decode('utf-8')
    header = migrate_auxiliary_section(original_header)
    base_path = config / 'printer_base.cfg'
    base = base_override if base_override is not None else base_path.read_text(encoding='utf-8')
    marker = home / '.local/share/lugoware/variant.json'
    previous = json.loads(marker.read_text())['variant'] if marker.exists() else None
    experimental = bool(section(header, AUX[0]) or section(base, SENSOR)
                        or '[include toolhead_auxiliary.cfg]' in header)
    changes = {}
    if variant == 'standard' and previous != 'toolhead' and not experimental:
        organized = organize_printer_header(header)
        if organized != original_header:
            changes[header_path] = organized.encode()
        changes[marker] = json.dumps({'variant': variant}).encode()
        new = add_dock_retry(paused_tools.strip_config(base), assets)
        new = plan_paused_tools(home, assets, new, variant, screen_override, changes)
        if new != base:
            changes[base_path] = new.encode()
        return changes
    auxiliary = config / 'toolhead_auxiliary.cfg'
    if variant == 'toolhead':
        # Retain wiring/limits, but apply the explicitly requested release PID.
        blocks = [section(header, n) for n in AUX]
        if all(blocks):
            content = ''.join(m[0] for m in blocks)
        elif auxiliary.exists():
            content = auxiliary.read_text(encoding='utf-8')
        else:
            content = (assets / 'toolhead_auxiliary.cfg').read_text(encoding='utf-8')
        # Upgrade existing auxiliary configs as well as fresh installations.
        defaults = (assets / 'toolhead_auxiliary.cfg').read_text(encoding='utf-8')
        content = apply_release_tuning(migrate_auxiliary_section(content), defaults)
        for name in ('gcode_macro TOOLHEAD_IDLE_STATE', 'delayed_gcode turn_off_toolhead'):
            content = remove_section(content, name).rstrip() + '\n\n' + section(defaults, name)[0]
        changes[auxiliary] = pid_profile(content, 'heater_generic Toolhead', TOOLHEAD_PID).encode()
    for name in AUX:
        header = remove_section(header, name)
    if variant == 'standard':
        # SAVE_CONFIG may have written heater PID into the generated trailer.
        header = re.sub(r'(?ms)^#\*# \[heater_generic Toolhead\]\n.*?(?=^#\*# \[|\Z)', '', header)
    header = re.sub(r'(?m)^\[include toolhead_auxiliary.cfg\]\s*\n', '', header)
    if variant == 'toolhead':
        header = '[include toolhead_auxiliary.cfg]\n' + header
    changes[header_path] = organize_printer_header(nozzle_header_profile(header, variant)).encode()
    base = toolchange_profile(paused_tools.strip_config(base), variant, assets)
    patches = json.loads((assets / 'ui_patches.json').read_text(encoding='utf-8'))
    for rel, edits in patches.items():
        path = home / rel
        old = path.read_text(encoding='utf-8')
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
        text = text.replace('</body>', '<script defer src="./lugoware-toolhead-temperature.js?v=1.2.30"></script></body>')
        changes[home / 'mainsail/lugoware-toolhead-temperature.js'] = (assets / 'lugoware-toolhead-temperature.js').read_bytes()
    changes[index] = text.encode()
    # Unused module files/auxiliary cfg remain for rollback, but no config loads
    # them in standard mode. The Mainsail script is likewise not included.
    changes[marker] = json.dumps({'variant': variant}).encode()
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
    changes = plan(home, variant, assets, base_override)
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
    if variant == 'standard' and previous != 'toolhead' and not experimental:
        return
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
