"""Bootstrap with interactive sudo once; grants one service-restricted bridge only."""
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys


def install(user):
    if os.geteuid() != 0 or not re.fullmatch('[a-z_][a-z0-9_-]*', user):
        raise ValueError('Run this installer via sudo with the printer account name')
    account = pwd.getpwnam(user)
    if account.pw_dir != '/home/' + user:
        raise ValueError('Unexpected printer home directory')
    from install_timezone import install_permission
    install_permission(user)
    source = Path(__file__).resolve().parent
    root = Path('/opt/lugoware/update-runtime')
    root.mkdir(parents=True, exist_ok=True, mode=0o755)
    (root / 'bin').mkdir(exist_ok=True, mode=0o755)
    for folder in (root, root / 'bin'):
        if folder.is_symlink():
            raise PermissionError('Unexpected symlink in update runtime')
        os.chown(folder, 0, 0)
        folder.chmod(0o755)
    for path in source.glob('*.py'):
        target = root / path.name
        if target.is_symlink():
            raise PermissionError('Unexpected runtime file symlink')
        shutil.copyfile(path, target)
        os.chown(target, 0, 0)
        target.chmod(0o755 if path.name == 'update_root.py' else 0o644)
    assets = root / 'toolhead_variant'
    if assets.is_symlink():
        raise PermissionError('Unexpected variant asset symlink')
    assets.mkdir(exist_ok=True)
    os.chown(assets, 0, 0)
    assets.chmod(0o755)
    for name in ('ui_patches.json', 'translations.json', 'toolhead_auxiliary.cfg', 'lugoware-toolhead-temperature.js', 'toolhead_temperature_test.py', 'temperature_toolhead_sensor.py', 'detachable_heater_sensor.py'):
        target = assets / name
        if target.is_symlink():
            raise PermissionError('Unexpected variant file symlink')
        shutil.copyfile(source / 'toolhead_variant' / name, target)
        os.chown(target, 0, 0)
        target.chmod(0o644)
    shim = root / 'bin/sudo'
    shutil.copyfile(source / 'update_sudo.py', shim)
    os.chown(shim, 0, 0)
    shim.chmod(0o755)
    cfg = Path('/etc/lugoware-updates.json')
    cfg.write_text(json.dumps({'user': user, 'uid': account.pw_uid}))
    cfg.chmod(0o644)
    rule = root / 'sudoers.pending'
    rule.write_text(f'{user} ALL=(root) NOPASSWD: /opt/lugoware/update-runtime/update_root.py\n')
    rule.chmod(0o440)
    subprocess.run(['/usr/sbin/visudo', '-cf', str(rule)], check=True)
    target = Path('/etc/sudoers.d/lugoware-updates')
    shutil.copyfile(rule, target)
    os.chown(target, 0, 0)
    target.chmod(0o440)
    marker = Path('/var/lib/lugoware-updates/active-release')
    if marker.exists():
        shutil.copy2(marker, marker.with_name('active-release.before-bootstrap'))
        marker.unlink()


if __name__ == '__main__':
    install(sys.argv[1])
