import json, os
from pathlib import Path
PATH = Path.home()/'.local/share/lugoware/first_run.json'
def read():
    try: return json.loads(PATH.read_text())
    except (OSError, ValueError): return {}
def pending(): return read().get('status') in ('pending', 'resetting', 'failed')
def save(data):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix('.tmp')
    with tmp.open('w') as f:
        json.dump(data, f); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, PATH)
