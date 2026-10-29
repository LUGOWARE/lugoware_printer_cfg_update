"""Migrate only print policy hooks; retain each model's motion and calibration."""
import re


def header(text, config_dir):
    if re.search(r'^\[screen_mesh\]\s*$', text, re.M):
        return text
    block = '[screen_mesh]\npath: ' + str(config_dir / '.screen_last_mesh.json') + '\n\n'
    marker = '#*# <---------------------- SAVE_CONFIG ---------------------->'
    if marker in text:
        return text.replace(marker, block + marker, 1)
    return text.rstrip() + '\n\n' + block


def config(text):
    match = re.search(r'(?ms)^\[gcode_macro START_PRINT\][^\n]*\n.*?(?=^\[|\Z)', text)
    if not match:
        raise ValueError('Missing START_PRINT for mesh policy')
    block = match.group()
    if 'SCREEN_MESH_PREPARE' not in block:
        block, count = re.subn(r'(?m)^(\s*)BED_MESH_CALIBRATE\s*(?:#[^\n]*)?$',
                               r'\1SCREEN_MESH_PREPARE', block)
        if count != 1:
            raise ValueError('Expected exactly one START_PRINT bed mesh command')
    if len(re.findall(r'(?m)^\s*SCREEN_MESH_PREPARE\s*$', block)) != 1:
        raise ValueError('Duplicate mesh preparation in START_PRINT')
    if re.search(r'(?m)^\s*BED_MESH_CALIBRATE\b', block):
        raise ValueError('START_PRINT bypasses mesh selection')
    # Explicitly clear a previous/native sensor choice before every print.
    begin = re.search(r'(?m)^( *)PRINT_SENSOR_BEGIN\s*$', block)
    if begin is None:
        raise ValueError('Missing PRINT_SENSOR_BEGIN')
    off = begin[1] + 'SET_FILAMENT_SENSOR SENSOR=encoder_sensor ENABLE=0\n'
    if off + begin[0] not in block:
        block = block[:begin.start()] + off + block[begin.start():]
    if 'SCREEN_MESH_AUDIT' not in block:
        block = re.sub(r'(?m)^( *)CHANGE_TOOL ([^\n]+)$',
                       r'\1CHANGE_TOOL \2\n\1SCREEN_MESH_AUDIT', block, count=1)
    # Mesh completion is followed by remaining preheat, not printing yet.
    block = re.sub(r'(SCREEN_MESH_PREPARE\s*\n\s*M117 )PRINTING\.\.\.',
                   r'\1Heating...', block, flags=re.I)
    return text[:match.start()] + block + text[match.end():]
