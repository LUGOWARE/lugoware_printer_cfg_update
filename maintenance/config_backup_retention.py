"""Keep three Klipper SAVE_CONFIG backups; run outside the Klipper reactor."""
import argparse
import datetime
import fcntl
import os
from pathlib import Path
import re
import subprocess
import sys
import time

PATTERN = re.compile(r'printer-(\d{8}_\d{6})\.cfg\Z')

def prune(folder, now=None):
    folder = Path(folder)
    now = time.time() if now is None else now
    primary = folder / 'printer.cfg'
    if primary.is_symlink() or not primary.is_file() or primary.stat().st_size == 0:
        return []
    candidates = []
    for path in folder.iterdir():
        match = PATTERN.fullmatch(path.name)
        if not match or path.is_symlink() or not path.is_file():
            continue
        try:
            datetime.datetime.strptime(match.group(1), '%Y%m%d_%H%M%S')
        except ValueError:
            continue
        candidates.append(path)
    # Avoid touching a SAVE_CONFIG rename sequence or fresh backups.
    if any(now - p.stat().st_mtime < 60 for p in candidates):
        return []
    candidates.sort(key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
    removed = []
    for path in candidates[3:]:
        if primary.is_file() and primary.stat().st_size and not path.is_symlink():
            path.unlink()
            removed.append(path.name)
    return removed

def install():
    home = Path.home()
    target = home / '.local/share/lugoware/config_backup_retention.py'
    target.parent.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).read_bytes()
    tmp = target.with_suffix('.tmp')
    tmp.write_bytes(source)
    os.replace(tmp, target)
    result = subprocess.run(['crontab', '-l'], capture_output=True, text=True,
                            env=dict(os.environ, LC_ALL='C'))
    if result.returncode and 'no crontab for' not in result.stderr.lower():
        raise RuntimeError(result.stderr)
    previous = result.stdout if result.returncode == 0 else ''
    backup = Path(os.environ.get('BACKUP_DIR', str(home / 'lugoware_backups/config-retention')))
    backup.mkdir(parents=True, exist_ok=True)
    (backup / ('user-crontab-%s.txt' % time.time_ns())).write_text(previous)
    lines = [line for line in previous.splitlines() if not line.endswith('# lugoware-config-backups')]
    lines.append('* * * * * /usr/bin/python3 "$HOME/.local/share/lugoware/config_backup_retention.py" # lugoware-config-backups')
    subprocess.run(['crontab', '-'], input='\n'.join(lines)+'\n', text=True, check=True)
    print('SAVE_CONFIG backup retention installed: latest 3 backups.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    if args.install:
        install()
    else:
        lock = Path.home() / '.local/share/lugoware/config-backups.lock'
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                sys.exit(0)
            prune(Path.home() / 'printer_data/config')
