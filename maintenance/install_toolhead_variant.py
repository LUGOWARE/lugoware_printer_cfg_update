"""M5P opt-in auxiliary heater profile. Pure planning before transactional writes."""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import stat

VARIANTS = ('standard', 'toolhead')
SENSOR = 'temperature_toolhead_sensor toolhead_sensor'
AUX = ('toolhead_temperature_test', 'heater_generic Toolhead')
NOZZLE_PID = dict(control='pid', pid_kp='13.953', pid_ki='0.511', pid_kd='95.230')
TOOLHEAD_PID = dict(control='pid', pid_kp='37.681', pid_ki='9.191', pid_kd='38.623')


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


def plan(home, variant, assets, base_override=None):
    if variant not in VARIANTS:
        raise ValueError('Invalid variant')
    config = home / 'printer_data/config'
    header_path = config / 'printer.cfg'
    header = header_path.read_text(encoding='utf-8')
    base_path = config / 'printer_base.cfg'
    base = base_override if base_override is not None else base_path.read_text(encoding='utf-8')
    marker = home / '.local/share/lugoware/variant.json'
    previous = json.loads(marker.read_text())['variant'] if marker.exists() else None
    experimental = bool(section(header, AUX[0]) or section(base, SENSOR)
                        or '[include toolhead_auxiliary.cfg]' in header)
    changes = {}
    if variant == 'standard' and previous != 'toolhead' and not experimental:
        # Ordinary standard machines keep byte-identical config/UI behavior.
        changes[marker] = json.dumps({'variant': variant}).encode()
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
        changes[auxiliary] = pid_profile(content, 'heater_generic Toolhead', TOOLHEAD_PID).encode()
    for name in AUX:
        header = remove_section(header, name)
    if variant == 'standard':
        # SAVE_CONFIG may have written heater PID into the generated trailer.
        header = re.sub(r'(?ms)^#\*# \[heater_generic Toolhead\]\n.*?(?=^#\*# \[|\Z)', '', header)
    header = re.sub(r'(?m)^\[include toolhead_auxiliary.cfg\]\s*\n', '', header)
    if variant == 'toolhead':
        header = '[include toolhead_auxiliary.cfg]\n' + header
    changes[header_path] = nozzle_header_profile(header, variant).encode()
    changes[base_path] = base_profile(base, variant).encode()
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
    if variant == 'toolhead':
        for name in ('toolhead_temperature_test.py', 'temperature_toolhead_sensor.py', 'detachable_heater_sensor.py'):
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
        text = text.replace('</body>', '<script defer src="./lugoware-toolhead-temperature.js?v=1.2.14"></script></body>')
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


def preflight(home, variant, assets, screen_upgrade_pending=None):
    """Check package integrity and non-replaced UI before system mutations."""
    patches = json.loads((assets / 'ui_patches.json').read_text(encoding='utf-8'))
    json.loads((assets / 'translations.json').read_text(encoding='utf-8'))
    for name in ('toolhead_temperature_test.py', 'temperature_toolhead_sensor.py', 'detachable_heater_sensor.py'):
        ast.parse((assets / name).read_bytes())
    for name in ('toolhead_auxiliary.cfg', 'lugoware-toolhead-temperature.js'):
        if not (assets / name).read_bytes():
            raise ValueError('Empty variant package asset: ' + name)
    marker = home / '.local/share/lugoware/variant.json'
    previous = json.loads(marker.read_text())['variant'] if marker.exists() else None
    if previous is not None and previous not in VARIANTS:
        raise ValueError('Invalid stored hardware profile; inspect variant.json')
    header = (home / 'printer_data/config/printer.cfg').read_text(encoding='utf-8')
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
        # The common installer always replaces this managed panel.
        if rel == 'KlipperScreen/panels/tool_prepare.py':
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
    header = (cfg / 'printer.cfg').read_text(encoding='utf-8')
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
