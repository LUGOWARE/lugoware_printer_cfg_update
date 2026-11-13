"""Prepare validated changes; caller owns backups and writes. No services or motion."""
import ast
import json
import re
from pathlib import Path


def patch_sd(source, assets):
    before, after = json.loads((assets/'virtual_sd_work.json').read_text(encoding='utf-8'))
    node = next(n for n in ast.walk(ast.parse(source))
                if isinstance(n, ast.FunctionDef) and n.name == 'work_handler')
    lines = source.splitlines(True)
    actual = ''.join(lines[node.lineno-1:node.end_lineno]).rstrip()+'\n'
    if actual == after:
        return source
    if actual != before:
        raise ValueError('Unsupported VirtualSD work_handler; no files changed')
    lines[node.lineno-1:node.end_lineno] = [after]
    result = ''.join(lines)
    compile(result, 'virtual_sdcard.py', 'exec')
    return result


def patch_screen(source):
    old = '                "print_sensor": None,'
    new = old+'\n                "lugo_preanalysis": None,'
    if '"lugo_preanalysis": None' not in source:
        if source.count(old) != 1:
            raise ValueError('Missing recovery subscription anchor')
        source = source.replace(old, new, 1)
    old = '    def process_update(self, *args):\n'
    new = old+'''        if args and args[0] == 'notify_status_update' and len(args) > 1:
            from ks_includes.preanalysis_ui import update
            update(self, args[1])
'''
    if new not in source:
        if source.count(old) != 1:
            raise ValueError('Missing screen status update anchor')
        source = source.replace(old, new, 1)
    compile(source, 'screen.py', 'exec')
    return source


def extend_changes(changes, home, screen, klipper, assets=None):
    assets = Path(assets) if assets else Path(__file__).with_name('preanalysis')
    def read(path):
        return changes[path].decode('utf-8') if path in changes else path.read_text(encoding='utf-8')
    extras = klipper/'klippy/extras'
    for name in ('lugo_preanalysis', 'preanalysis_worker', 'preanalysis_eta_worker',
                 'cache_cleanup_worker', 'recovery_latency', 'recovery_worker',
                 'lugo_tool_temperature', 'exclude_tool_guard'):
        changes[extras/(name+'.py')] = (assets/(name+'.py')).read_bytes()
    path = extras/'virtual_sdcard.py'
    changes[path] = patch_sd(read(path), assets).encode('utf-8')
    changes[screen/'ks_includes/preanalysis_ui.py'] = (assets/'preanalysis_ui.py').read_bytes()
    path = screen/'screen.py'
    changes[path] = patch_screen(read(path)).encode('utf-8')
    path = home/'printer_data/config/printer.cfg'
    source = read(path)
    if not re.search(r'^\[lugo_preanalysis\]\s*(?:#.*)?$', source, re.M):
        marker = '#*# <---------------------- SAVE_CONFIG ---------------------->'
        block = '\n[lugo_preanalysis]\n\n'
        source = source.replace(marker, block+marker, 1) if marker in source else source.rstrip()+'\n'+block
    changes[path] = source.encode('utf-8')
