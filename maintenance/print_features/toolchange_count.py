"""Count the explicit tool selections used by the LUGOWARE print macros."""
import re
import hashlib
import json
import os
from pathlib import Path


def count_toolchanges(lines):
    current = None
    total = 0
    for line in lines:
        code = line.split(';', 1)[0].strip()
        if not code:
            continue
        command = code.split()[0].upper()
        target = None
        if command == 'START_PRINT':
            match = re.search(r'\bINITIAL_TOOL=(\d+)\b', code, re.I)
            target = int(match.group(1)) if match else 0
        elif command == 'CHANGE_TOOL':
            match = re.search(r'\bNEXT_TOOL=(\d+)\b', code, re.I)
            if match:
                target = int(match.group(1))
        elif re.fullmatch(r'T\d+', command):
            target = int(command[1:])
        if target is not None and target != current:
            total += 1
            current = target
    return total


def file_total(root, filename, cache_dir=None):
    base = Path(root).expanduser().resolve()
    path = (base / filename).resolve()
    path.relative_to(base)
    stat = path.stat()
    identity = [str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino]
    cache_dir = Path(cache_dir) if cache_dir is not None else Path.home() / '.cache/KlipperScreen/toolchanges'
    key = hashlib.sha256(str(path).encode()).hexdigest()
    cache = cache_dir / (key + '.json')
    try:
        saved = json.loads(cache.read_text())
        if saved['identity'] == identity and type(saved['total']) is int and saved['total'] >= 0:
            return saved['total']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    with path.open(errors='replace') as stream:
        total = count_toolchanges(stream)
    after = path.stat()
    if identity != [str(path), after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_ino]:
        raise ValueError('G-code changed during toolchange scan')
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix('.' + str(os.getpid()) + '.tmp')
        temporary.write_text(json.dumps({'identity': identity, 'total': total}))
        os.replace(temporary, cache)
    except OSError:
        pass  # A read-only cache must not prevent displaying the result.
    return total


if __name__ == '__main__':
    import sys
    try:
        if hasattr(os, 'nice'):
            os.nice(10)
        print(json.dumps({'total': file_total(sys.argv[1], sys.argv[2])}))
    except (OSError, ValueError, IndexError):
        print(json.dumps({'total': None}))
