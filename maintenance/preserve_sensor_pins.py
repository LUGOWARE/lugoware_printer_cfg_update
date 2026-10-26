"""Retain machine-specific sensor wiring when replacing the model profile."""
import argparse
import glob
import re
from pathlib import Path

HEADER = re.compile(r'^\[([^\]]+)\]\s*(?:[#;].*)?$')
PIN = re.compile(r'^\s*sensor_pin\s*[:=]\s*([^#;\n]+)')


def sensor_pins(path, stack=()):
    path = path.resolve()
    if path in stack:
        raise ValueError('Recursive config include: ' + str(path))
    pins, section = {}, None
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if line.startswith('#*#'):
            continue
        match = HEADER.match(line)
        if match:
            section = match[1]
            if section.startswith('include '):
                pattern = str(path.parent / section[8:].strip())
                matches = sorted(glob.glob(pattern))
                if not matches and not glob.has_magic(pattern):
                    raise ValueError('Missing config include: ' + pattern)
                for included in matches:
                    pins.update(sensor_pins(Path(included), stack + (path,)))
                section = None
            continue
        match = PIN.match(line)
        if match and section and not section.startswith(('gcode_macro ', 'delayed_gcode ')):
            pins[section] = match[1].strip()
    return pins


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
    return ''.join(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('template', type=Path)
    parser.add_argument('current', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    text = preserve(args.template.read_text(encoding='utf-8-sig'), args.current)
    args.output.write_bytes(text.encode('utf-8'))
