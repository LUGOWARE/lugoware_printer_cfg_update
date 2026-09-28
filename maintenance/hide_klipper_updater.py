"""Disable only Moonraker's built-in Klipper updater, retaining other updaters."""
import argparse
import ast
import os
from pathlib import Path
import shutil
import tempfile

MARKER = '# LUGOWARE: built-in Klipper updater disabled'


def replacement(text):
    tree = ast.parse(text)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'UpdateManager']
    if len(classes) != 1:
        raise ValueError('Unsupported Moonraker UpdateManager structure')
    methods = {n.name: n for n in classes[0].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    required = ('__init__', '_set_klipper_repo', '_update_klipper_repo', 'register_updater')
    if any(name not in methods for name in required):
        raise ValueError('Required Moonraker updater methods missing; no changes made')
    if MARKER in text:
        if text.count(MARKER) != 4:
            raise ValueError('Incomplete updater patch; no changes made')
        return text, False
    # Keep event signalling, but prevent all paths which register Klipper again.
    lines = text.splitlines(keepends=True)
    nl = '\r\n' if '\r\n' in text else '\n'
    additions = []
    init = methods['__init__']
    additions.append((init.end_lineno, [MARKER, "self.updaters.pop('klipper', None)"]))
    setter = methods['_set_klipper_repo']
    first = setter.body[0]
    if not isinstance(first, ast.If) or 'self.klippy_identified_evt.set()' not in ast.unparse(first):
        raise ValueError('Unknown Klipper identification event handling; no changes made')
    additions.append((first.end_lineno, [MARKER, 'return']))
    additions.append((methods['_update_klipper_repo'].body[0].lineno - 1, [MARKER, 'return']))
    additions.append((methods['register_updater'].body[0].lineno - 1,
                      [MARKER, "if name == 'klipper':", '    return']))
    for index, body in sorted(additions, reverse=True):
        lines[index:index] = ['        ' + line + nl for line in body]
    result = ''.join(lines)
    compile(result, '<patched update_manager>', 'exec')
    return result, True


def patch(path, backup, check=False):
    original = path.read_bytes()
    result, changed = replacement(original.decode('utf-8'))
    if check or not changed:
        return changed
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(path, backup)
    fd, temporary = tempfile.mkstemp(prefix='.lugoware-updater-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(result.encode('utf-8'))
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('backup', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print('changed' if patch(args.path, args.backup, args.check) else 'already patched')
