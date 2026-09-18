"""Restore the maintained extension before Klipper starts."""
import ast
import os
from pathlib import Path
import sys
import tempfile


def install(folder, source):
    data = source.read_bytes()
    ast.parse(data)
    target = folder / 'klippy/extras/multi_pin.py'
    if target.read_bytes() != data:
        fd, name = tempfile.mkstemp(prefix='.multi-pin-', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
            os.chmod(name, 0o644)
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    # Avoid a cached module surviving a same-size/same-second replacement.
    for cached in list((target.parent / '__pycache__').glob('multi_pin.*.pyc')) + [target.with_suffix('.pyc')]:
        if cached.exists():
            cached.unlink()
    if target.read_bytes() != data:
        raise RuntimeError('Extension verification failed')


if __name__ == '__main__':
    install(Path(sys.argv[1]), Path(__file__).with_name('multi_pin.py'))
