"""Private read-only recovery index worker. Never imports Klipper objects."""
import json
import os
from pathlib import Path
import sys

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Expected source path')
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from recovery_index import analyze
    print(json.dumps(analyze(Path(sys.argv[1])), allow_nan=False))
