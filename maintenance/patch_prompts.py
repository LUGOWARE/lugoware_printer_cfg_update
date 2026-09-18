"""Patch only the known prompt_text branch; refuse unfamiliar implementations."""
import ast
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


def replacement(text):
    marker = re.compile(r'^(?P<i>[ \t]*)elif data\.startswith\("prompt_text"\):\r?$', re.MULTILINE)
    matches = list(marker.finditer(text))
    if len(matches) != 1:
        raise ValueError('ERROR: expected exactly one prompt_text block')
    start = matches[0].start()
    indent = matches[0].group('i')
    nl = '\r\n' if '\r\n' in text else '\n'
    unit = '\t' if '\t' in indent else '    '
    original = nl.join([
        indent + 'elif data.startswith("prompt_text"):',
        indent + unit + 'self.text = data.replace("prompt_text ", "")',
        indent + unit + 'return', ''])
    patched = nl.join([
        indent + 'elif data.startswith("prompt_text"):',
        indent + unit + 'new_text = data.replace("prompt_text ", "", 1)',
        indent + unit + 'if self.text:',
        indent + unit * 2 + 'self.text += "\\n" + new_text',
        indent + unit + 'else:',
        indent + unit * 2 + 'self.text = new_text',
        indent + unit + 'return', ''])
    if text.startswith(patched, start):
        ast.parse(text)
        return text, False
    if not text.startswith(original, start):
        raise ValueError('ERROR: prompt_text block differs from expected code; no changes made')
    result = text[:start] + patched + text[start + len(original):]
    ast.parse(result)
    return result, True


def patch(path, check=False):
    data = path.read_bytes()
    result, changed = replacement(data.decode('utf-8'))
    if check or not changed:
        return changed
    backup = path.with_name(path.name + '.backup')
    try:
        with backup.open('xb') as stream:
            stream.write(data)
    except FileExistsError:
        pass  # Preserve the first backup across future installations.
    fd, temporary = tempfile.mkstemp(prefix='.prompts-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(result.encode('utf-8'))
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


if __name__ == '__main__':
    try:
        changed = patch(Path(sys.argv[1]), '--check' in sys.argv[2:])
        print('changed' if changed else 'already patched')
    except Exception as exc:
        raise SystemExit(str(exc))
