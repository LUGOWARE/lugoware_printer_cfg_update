"""Retain machine-specific sensor wiring and motor currents on profile updates."""
import argparse
import glob
import re
from pathlib import Path

HEADER = re.compile(r'^\[([^\]]+)\]\s*(?:[#;].*)?$')
PIN = re.compile(r'^\s*sensor_pin\s*[:=]\s*([^#;\n]+)')
DRIVER = re.compile(r'^tmc\d+\s+\S', re.I)
CURRENT = re.compile(r'^(\s*)(run_current|hold_current)(\s*[:=]\s*)([^#;\r\n]+)', re.I)


def config_options(path, read_option, stack=()):
    path = path.resolve()
    if path in stack:
        raise ValueError('Recursive config include: ' + str(path))
    options, section = {}, None
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if line.startswith('#*#'):
            continue
        match = HEADER.match(line)
        if match:
            section = match[1].strip()
            if section.startswith('include '):
                pattern = str(path.parent / section[8:].strip())
                matches = sorted(glob.glob(pattern))
                if not matches and not glob.has_magic(pattern):
                    raise ValueError('Missing config include: ' + pattern)
                for included in matches:
                    for name, values in config_options(Path(included), read_option, stack + (path,)).items():
                        options.setdefault(name, {}).update(values)
                section = None
            elif DRIVER.match(section):
                options.setdefault(section, {})
            continue
        if section and not section.startswith(('gcode_macro ', 'delayed_gcode ')):
            option = read_option(section, line)
            if option:
                key, value = option
                options.setdefault(section, {})[key] = value
    return options


def sensor_pins(path):
    def read_pin(section, line):
        match = PIN.match(line)
        if match:
            return 'sensor_pin', match[1].strip()

    return {name: values['sensor_pin'] for name, values in config_options(path, read_pin).items()
            if 'sensor_pin' in values}


def preserve_motor_currents(template, current):
    def read_current(section, line):
        match = CURRENT.match(line) if DRIVER.match(section) else None
        if match:
            return match[2].lower(), match[4].strip()

    existing = {name: values for name, values in config_options(current, read_current).items()
                if DRIVER.match(name) and 'run_current' in values}
    if not existing:
        return template
    newline = '\r\n' if '\r\n' in template else '\n'
    output, pending = [], {}
    previous = None
    for line in template.splitlines(keepends=True):
        header = HEADER.match(line.rstrip('\r\n'))
        if header:
            output.extend(f'{key}: {value}{newline}' for key, value in pending.items())
            previous = existing.get(header[1].strip())
            pending = dict(previous or {})
        match = CURRENT.match(line) if previous is not None else None
        if match:
            key = match[2].lower()
            if key not in previous:
                # Omitting hold_current keeps Klipper's existing default.
                continue
            value = pending.pop(key, previous[key])
            start, end = match.span(4)
            original = match[4]
            line = line[:start] + value + original[len(original.rstrip()):] + line[end:]
        output.append(line)
    if pending:
        if output and not output[-1].endswith(('\n', '\r')):
            output.append(newline)
        output.extend(f'{key}: {value}{newline}' for key, value in pending.items())
    return ''.join(output)


def preserve(template, current):
    pins = sensor_pins(current)
    section, output = None, []
    for line in template.splitlines(keepends=True):
        match = HEADER.match(line.rstrip('\r\n'))
        if match:
            section = match[1]
        if section in pins and PIN.match(line):
            line = 'sensor_pin: ' + pins[section] + '\n'
        output.append(line)
    return preserve_motor_currents(''.join(output), current)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('template', type=Path)
    parser.add_argument('current', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    text = preserve(args.template.read_text(encoding='utf-8-sig'), args.current)
    args.output.write_bytes(text.encode('utf-8'))
