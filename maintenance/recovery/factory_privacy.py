#!/usr/bin/python3 -I
"""Root-owned, fixed-scope factory cleanup. Never installed in a writable directory."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time

HOME = Path('/home/biqu')
SELF = '/usr/local/libexec/lugoware-factory-privacy'
STATUS = Path('/var/lib/lugoware-factory/privacy.json')
BACKUPS = ('lugoware_backups', 'lugoware_m8p_backups')
HISTORY = ('.bash_history', '.zsh_history', '.python_history', '.lesshst',
           '.local/share/fish/fish_history')

def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True,
                          timeout=60, env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL':'C'}).stdout

def open_dir(path):
    """Walk without following ANY symlink, including user-controlled ancestors."""
    path = Path(path)
    if not path.is_absolute():
        raise RuntimeError('Absolute path required')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        return fd
    except BaseException:
        os.close(fd)
        raise

def remove_entry(fd, name, truncate=False):
    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
    if stat.S_ISDIR(info.st_mode):
        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            if os.fstat(child).st_dev != os.fstat(fd).st_dev:
                raise RuntimeError('Refusing mounted directory')
            for item in os.listdir(child):
                remove_entry(child, item, truncate)
        finally:
            os.close(child)
        if not truncate:
            os.rmdir(name, dir_fd=fd)
    elif truncate and stat.S_ISREG(info.st_mode):
        out = os.open(name, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            actual = os.fstat(out)
            if not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1:
                raise RuntimeError('Refusing non-regular or hard-linked log')
            os.ftruncate(out, 0)
        finally:
            os.close(out)
    elif not truncate or stat.S_ISLNK(info.st_mode):
        os.unlink(name, dir_fd=fd)

def clear(path, contents=False, truncate=False):
    try:
        fd = open_dir(path if contents else Path(path).parent)
    except FileNotFoundError:
        return
    try:
        names = os.listdir(fd) if contents else [Path(path).name]
        for name in names:
            try:
                remove_entry(fd, name, truncate)
            except FileNotFoundError:
                pass
    finally:
        os.close(fd)

def wifi_profiles():
    rows = run('/usr/bin/nmcli', '-t', '-f', 'UUID,TYPE', 'connection', 'show')
    result = []
    for line in rows.splitlines():
        uuid, kind = line.split(':', 1)
        if kind in ('802-11-wireless', 'wifi'):
            if not re.fullmatch(r'[0-9a-fA-F-]{36}', uuid):
                raise RuntimeError('Invalid connection UUID')
            result.append(uuid)
    return result

def check():
    if os.geteuid() != 0:
        raise RuntimeError('Administrator helper required')
    if not shutil.which('nmcli') or not shutil.which('systemd-run'):
        raise RuntimeError('NetworkManager and systemd-run are required')
    profiles = wifi_profiles()  # Also verifies the NetworkManager connection.
    # Reject altered parent paths before destructive operations begin.
    for path in (HOME, HOME/'printer_data', Path('/var/log')):
        os.close(open_dir(path))
    for name in BACKUPS:
        p = HOME/name
        if p.exists() or p.is_symlink():
            os.close(open_dir(p))
    # Do not let a logged-in shell write old in-memory history after cleanup.
    processes = run('/bin/ps', '-u', 'biqu', '-o', 'comm=,tty=')
    shells = {'bash', 'zsh', 'fish', 'sh', 'dash', 'ksh'}
    if any(len(parts := row.split()) == 2 and parts[0] in shells and
           parts[1] != '?' for row in processes.splitlines()):
        raise RuntimeError('Close interactive SSH/local terminals before factory reset')
    return {'wifi_profiles':len(profiles), 'privacy_cleanup_version':1}

def clean():
    check()
    for name in BACKUPS:
        clear(HOME/name, contents=True)
    for root in (HOME, Path('/root')):
        for name in HISTORY:
            clear(root/name)
    clear(HOME/'printer_data/logs', contents=True, truncate=True)
    # These are log locations only; configurations, SSH keys and firmware stay intact.
    for name in ('syslog','auth.log','kern.log','daemon.log','messages','debug',
                 'wtmp','btmp','lastlog','faillog','alternatives.log','dpkg.log'):
        for item in Path('/var/log').glob(name+'*'):
            if item.name == name:
                clear(item, truncate=True)
            elif item.is_file() or item.is_symlink():
                clear(item)
    for folder in ('apt','nginx','private'):
        clear(Path('/var/log')/folder, contents=True, truncate=True)
    # Rotate first so historical journal files can be removed. New events remain normal.
    run('/bin/journalctl','--rotate')
    time.sleep(1.1)
    run('/bin/journalctl','--vacuum-time=1s')

def status(value, **extra):
    STATUS.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    temp = STATUS.with_suffix('.tmp')
    temp.write_text(json.dumps({'status':value, **extra}))
    temp.chmod(0o644)
    temp.replace(STATUS)

def finish():
    # Already running as an independent systemd service: SSH disconnect cannot stop it.
    try:
        for uuid in wifi_profiles():
            run('/usr/bin/nmcli','connection','delete','uuid',uuid)
        if wifi_profiles():
            raise RuntimeError('Wi-Fi profiles remain')
        devices = run('/usr/bin/nmcli','-t','-f','DEVICE,TYPE,STATE','device','status')
        for row in devices.splitlines():
            device, kind, state = row.split(':', 2)
            if kind == 'wifi' and state.startswith('connected'):
                run('/usr/bin/nmcli','device','disconnect',device)
        status('complete')
    except Exception as exc:
        status('failed', error=str(exc))
        raise

def schedule():
    # Delay until the SSH caller receives the acknowledgement. Ethernet is untouched.
    status('pending')
    try:
        run('/usr/bin/systemd-run','--unit=lugoware-factory-wifi','--on-active=20s',
            '--timer-property=AccuracySec=1s', '--collect', SELF, '--finish')
    except Exception as exc:
        status('failed', error=str(exc))
        raise

def main():
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise RuntimeError('Invalid invocation')
    action = sys.argv[1]
    if action == '--check':
        print(json.dumps(check()))
    elif action == '--clean':
        clean()
    elif action == '--schedule':
        schedule()
    elif action == '--finish':
        finish()
    else:
        raise RuntimeError('Unsupported action')

if __name__ == '__main__':
    main()
