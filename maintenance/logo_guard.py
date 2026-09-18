#!/usr/bin/env python3
"""Preserve the production splash assets across package and initramfs updates."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ASSETS = {
    'watermark.png': '/usr/share/plymouth/themes/armbian/watermark.png',
    'boot.bmp': '/boot/boot.bmp',
}
STORE = '/opt/lugoware/logo'


def path(root, name):
    return root / name.lstrip('/')


def valid(name, data):
    signature = b'\x89PNG\r\n\x1a\n' if name.endswith('.png') else b'BM'
    if not data.startswith(signature) or len(data) < 32:
        raise ValueError('Missing or invalid asset: ' + name)
    return data


def check(root):
    for name, dest in ASSETS.items():
        saved = path(root, STORE) / name
        source = saved if saved.exists() else path(root, dest)
        valid(name, source.read_bytes())


def atomic_write(dest, data, mode=0o644):
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.lugoware-', dir=dest.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, dest)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def backup(root):
    check(root)
    folder = path(root, STORE)
    folder.mkdir(parents=True, exist_ok=True)
    for name, dest in ASSETS.items():
        saved = folder / name
        # Existing production backups, including the GUI's backups, win.
        if not saved.exists():
            atomic_write(saved, valid(name, path(root, dest).read_bytes()))


def restore(root, force=False, run=subprocess.run):
    pending = path(root, STORE) / '.initramfs-pending'
    if force:
        pending.touch()
    for name, target in ASSETS.items():
        data = valid(name, (path(root, STORE) / name).read_bytes())
        dest = path(root, target)
        if not dest.exists() or dest.read_bytes() != data:
            if name == 'watermark.png':
                pending.touch()
            atomic_write(dest, data)
            print('Restored: ' + target, flush=True)
    # Keep a pending marker so an interrupted/failed rebuild is retried.
    if pending.exists():
        run(['update-initramfs', '-u', '-k', 'all'], check=True)
        pending.unlink()


HOOK = '''#!/bin/sh
set -eu
case "${1:-}" in prereqs) exit 0 ;; esac
src=/opt/lugoware/logo/watermark.png
test -s "$src"
install -D -m 644 "$src" "${DESTDIR:?}/usr/share/plymouth/themes/armbian/watermark.png"
'''
SERVICE = '''[Unit]
Description=LUGOWARE system maintenance
After=local-fs.target
RequiresMountsFor=/boot /opt/lugoware

[Service]
Type=oneshot
ExecStart=/opt/lugoware/restore-logo.sh

[Install]
WantedBy=multi-user.target
'''
APT = '''DPkg::Post-Invoke { "/opt/lugoware/restore-logo.sh >> /var/log/lugoware-maintenance.log 2>&1 || logger -t lugoware 'System maintenance failed; see maintenance log'"; };
'''
WRAPPER = '''#!/bin/sh
set -eu
exec /usr/bin/python3 /opt/lugoware/logo_guard.py restore
'''


def install(root, run=subprocess.run):
    backup(root)
    files = {
        '/opt/lugoware/logo_guard.py': (Path(__file__).read_bytes(), 0o644),
        '/opt/lugoware/restore-logo.sh': (WRAPPER.encode(), 0o755),
        '/etc/systemd/system/lugoware-logo.service': (SERVICE.encode(), 0o644),
        '/etc/apt/apt.conf.d/99lugoware-logo': (APT.encode(), 0o644),
        '/etc/initramfs-tools/hooks/zz-lugoware-logo': (HOOK.encode(), 0o755),
    }
    for target, (data, mode) in files.items():
        atomic_write(path(root, target), data, mode)
    run(['systemctl', 'daemon-reload'], check=True)
    run(['systemctl', 'enable', 'lugoware-logo.service'], check=True)
    run(['systemctl', 'is-enabled', '--quiet', 'lugoware-logo.service'], check=True)
    restore(root, force=True, run=run)


def verify(root, run=subprocess.run):
    for name, target in ASSETS.items():
        saved = valid(name, (path(root, STORE) / name).read_bytes())
        if path(root, target).read_bytes() != saved:
            raise RuntimeError('Protected asset mismatch: ' + target)
    for target, expected in (
        ('/opt/lugoware/restore-logo.sh', WRAPPER),
        ('/etc/systemd/system/lugoware-logo.service', SERVICE),
        ('/etc/apt/apt.conf.d/99lugoware-logo', APT),
        ('/etc/initramfs-tools/hooks/zz-lugoware-logo', HOOK),
    ):
        if path(root, target).read_text() != expected:
            raise RuntimeError('Protection configuration mismatch: ' + target)
    if path(root, '/opt/lugoware/logo_guard.py').read_bytes() != Path(__file__).read_bytes():
        raise RuntimeError('Restore implementation mismatch')
    if (path(root, STORE) / '.initramfs-pending').exists():
        raise RuntimeError('Boot image rebuild is still pending')
    run(['systemctl', 'is-enabled', '--quiet', 'lugoware-logo.service'], check=True)


def main():
    if os.geteuid() != 0:
        raise SystemExit('Root privileges required')
    import fcntl
    with open('/run/lock/lugoware-logo.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        action = sys.argv[1]
        if action in ('install', 'check'):
            if not shutil.which('update-initramfs'):
                raise SystemExit('initramfs-tools is required')
            check(Path('/'))
        if action == 'install':
            install(Path('/'))
        elif action == 'restore':
            restore(Path('/'))
        elif action == 'verify':
            verify(Path('/'))
        elif action != 'check':
            raise SystemExit('Unknown action')


if __name__ == '__main__':
    main()
