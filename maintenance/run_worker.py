#!/usr/bin/python3
"""Load complete verified releases and report failures before worker startup."""
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback

RUNTIME = Path('/opt/lugoware/update-runtime')
STATE = Path('/var/lib/lugoware-updates')


def trusted(path):
    for item in (path, *path.parents):
        info = item.lstat()
        if item.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022:
            raise PermissionError('Untrusted updater release path: ' + str(item))


def worker_source():
    marker = STATE / 'active-release'
    if not marker.exists():
        trusted(RUNTIME)
        return RUNTIME
    trusted(marker)
    commit = marker.read_text().strip()
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Invalid verified updater release')
    source = STATE / commit / 'maintenance'
    trusted(source)
    trusted(source / 'channel_worker.py')
    return source


def report_failure(channel, exc):
    home = Path.home()
    folder = home / '.local/share/lugoware'
    folder.mkdir(parents=True, exist_ok=True)
    log = home / 'printer_data/logs' / ('lugoware_' + channel + '.log')
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a') as stream:
        traceback.print_exc(file=stream)
    data = dict(channel=channel, state='failed', detail='Updater startup failed: ' + str(exc),
                run_id=str(time.time_ns()), time=time.time(), log=str(log))
    path = folder / (channel + '-status.json')
    temporary = path.with_suffix('.bootstrap.pending')
    temporary.write_text(json.dumps(data))
    os.replace(temporary, path)


def main(channel):
    if channel not in ('config', 'system'):
        raise ValueError('Unknown update channel')
    try:
        sys.path.insert(0, str(worker_source()))
        from channel_worker import run
    except Exception as exc:
        report_failure(channel, exc)
        raise
    run(channel)


if __name__ == '__main__':
    main(sys.argv[1])
