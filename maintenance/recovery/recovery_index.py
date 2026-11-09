"""Read-only, bounded recovery file analysis. No printer imports or commands."""
import bisect
import hashlib
import math
import re
try:
    from .recovery_objects import validate as validate_exclusion
except ImportError:
    from recovery_objects import validate as validate_exclusion

MARKER = re.compile(r'^;\s*(?:LAYER_CHANGE|CHANGE_LAYER)\s*$', re.I)
CURA = re.compile(r'^;\s*LAYER:\s*(\d+)\s*$', re.I)
HEIGHT = re.compile(r'^;\s*(?:Z:|Z_HEIGHT:)\s*([\d.+-]+)\s*$', re.I)


def analyze(path):
    before = path.stat()
    digest = hashlib.sha256()
    layers = []
    timeline = []
    offset = 0
    with path.open('rb') as stream:
        for raw in stream:
            digest.update(raw)
            line = raw.decode('utf-8', 'replace').strip()
            if line.upper().startswith('M73 '):
                remaining = re.search(r'\bR([\d.]+)\b', line, re.I)
                if remaining and len(timeline) < 100000:
                    seconds = float(remaining[1]) * 60.
                    if math.isfinite(seconds) and (not timeline or seconds <= timeline[-1]['remaining']):
                        timeline.append({'offset': offset, 'remaining': seconds})
            if MARKER.match(line) or CURA.match(line):
                if len(layers) >= 100000:
                    raise ValueError('Too many layers')
                layers.append({'offset': offset, 'layer': len(layers) + 1, 'height': None})
            elif layers:
                match = HEIGHT.match(line)
                if match:
                    value = float(match[1])
                    if math.isfinite(value): layers[-1]['height'] = value
            offset += len(raw)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Print file changed during recovery analysis')
    return {'identity': {'sha256': digest.hexdigest(), 'size': before.st_size,
                          'mtime_ns': before.st_mtime_ns}, 'layers': layers, 'timeline': timeline}


def locate(layers, offset):
    i = bisect.bisect_right([v['offset'] for v in layers], offset) - 1
    return dict(layers[i]) if i >= 0 else None


def validate_checkpoint(cp):
    if not cp or not cp.get('executed'):
        return 'No execution-confirmed checkpoint. This older record cannot resume automatically.'
    snap = cp.get('snapshot', {})
    tool = snap.get('gcode_macro TOOL_STATE', {})
    if tool.get('active_tool') not in range(4) or tool.get('changing'):
        return 'Tool change was not complete at this checkpoint.'
    if snap.get('fast_cancel', {}).get('phase') not in ('docked', 'normal'):
        return 'Docking state is not suitable for recovery.'
    reason = validate_exclusion(snap)
    if reason: return reason
    gm = snap.get('gcode_internal', {})
    if not gm or not gm.get('absolute_coord') or len(gm.get('last_position', [])) != 4:
        return 'Unsupported coordinate state.'
    numbers = (gm.get('last_position', []) + gm.get('base_position', []) + gm.get('homing_position', [])
               + [snap.get('extruder_rotation_distance', 0)])
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in numbers) or not snap.get('extruder_rotation_distance'):
        return 'Unsupported coordinate state.'
    if not snap.get('active_mesh'):
        return 'Checkpoint has no restorable mesh.'
    if not 0 < snap.get('extruder', {}).get('target', 0) <= 300:
        return 'Checkpoint temperature is not suitable for recovery.'
    return ''
