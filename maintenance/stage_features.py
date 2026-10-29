"""Print stages and clipped information scrolling; preserve machine settings."""
import json
import re
from pathlib import Path


def job(text, reverse=False):
    patches = json.loads(Path(__file__).with_name('print_features').joinpath('stage_ui.json').read_text(encoding='utf-8'))
    for old, new in (reversed(patches) if reverse else patches):
        if reverse:
            if new in text:
                text = text.replace(new, old, 1)
        elif new not in text:
            if text.count(old) != 1:
                raise ValueError('Unsupported stage UI anchor: ' + old[:100])
            text = text.replace(old, new, 1)
    return text


def screen(text):
    block = ('        from ks_includes.restart_notice import install as install_restart_notice\n'
             '        install_restart_notice(self)\n')
    if block not in text:
        anchor = '        self.initial_connection()\n'
        if text.count(anchor) != 1:
            raise ValueError('Unsupported screen initialization')
        text = text.replace(anchor, anchor+block)
    return text


def config(text):
    match = re.search(r'(?ms)^\[gcode_macro START_PRINT\]\n.*?(?=^\[|\Z)', text)
    if not match:
        return text
    block = match[0]
    if '# LUGOWARE print stage messages' in block:
        return text
    # Only change display messages; keep all movement and temperature commands.
    block = re.sub(r'(?m)^[ \t]*M117 (?:Bed Mesh\.\.\.|PRINTING\.\.\.)[ \t]*$', '', block)
    mesh_command = 'SCREEN_MESH_PREPARE' if 'SCREEN_MESH_PREPARE' in block else 'BED_MESH_CALIBRATE'
    for command, before, after in [('HOME_CHECK', 'Homing...', None),
                                    (mesh_command, 'Bed Mesh...', 'Heating...')]:
        pattern = r'(?m)^([ \t]*)' + command + r'[ \t]*$'
        def add(m):
            return m[1]+'M117 '+before+'\n'+m[0]+(('\n'+m[1]+'M117 '+after) if after else '')
        block, count = re.subn(pattern, add, block)
        if count != 1:
            raise ValueError('Unsupported START_PRINT: '+command)
    pos = block.rfind('{% endif %}')
    if pos < 0:
        raise ValueError('Missing START_PRINT closing guard')
    line = block.rfind('\n', 0, pos)+1
    block = block[:line]+'    M117 PRINTING...\n'+block[line:]
    block = block.replace('gcode:\n', 'gcode:\n    # LUGOWARE print stage messages\n', 1)
    return text[:match.start()]+block+text[match.end():]
