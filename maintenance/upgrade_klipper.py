"""Upgrade older hosts to the release baseline, including the Linux MCU."""
import argparse
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

BASELINE = 'f0892d82b0f1c1228454f09eb508eddde2250f4b'


def release(version):
    match = re.match(r'^v(\d+)\.(\d+)\.(\d+)(?:-|$)', version)
    if not match:
        raise ValueError('Cannot determine Klipper version: ' + version)
    return tuple(map(int, match.groups()))


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def upgrade(folder, backup, check=False):
    version = output('git', '-C', str(folder), 'describe', '--always', '--tags', '--long', '--dirty')
    pending = folder / '.git/lugoware-linux-mcu-pending'
    update_host = release(version) < (0, 13, 0)
    if not update_host and not pending.exists():
        print('[건너뜀] Klipper 본체: ' + version, flush=True)
        return
    changes = output('git', '-C', str(folder), 'diff', 'HEAD', '--name-only').splitlines()
    if set(changes) - {'klippy/extras/multi_pin.py'}:
        raise RuntimeError('Unrecognized local Klipper edits; preserved: ' + ', '.join(changes))
    if check:
        print('[예정] Klipper 및 CB2 MCU를 배포 기준으로 업데이트', flush=True)
        return
    backup.mkdir(parents=True, exist_ok=True)
    (backup / 'commit.txt').write_text(output('git', '-C', str(folder), 'rev-parse', 'HEAD'))
    (backup / 'changes.patch').write_bytes(subprocess.check_output(['git', '-C', str(folder), 'diff', '--binary', 'HEAD']))
    shutil.copy2(folder / 'klippy/extras/multi_pin.py', backup / 'multi_pin.py')
    shutil.copytree(Path.home() / 'printer_data/config', backup / 'config', dirs_exist_ok=True)
    run('sudo', 'cp', '-a', '/usr/local/bin/klipper_mcu', str(backup / 'klipper_mcu'))
    if update_host:
        run('git', '-C', str(folder), 'fetch', 'https://github.com/Klipper3d/klipper.git', BASELINE)
    # Use normal binary repositories, without changing the system's sources.
    # Old CB2 images can have only deb-src enabled and dead backports entries.
    with tempfile.TemporaryDirectory() as tmp:
        os.chmod(tmp, 0o755)
        sources = Path(tmp) / 'sources.list'
        codename = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line).get('VERSION_CODENAME', '').strip('"')
        if codename != 'bullseye':
            run('sudo', 'apt-get', 'update')
            options = []
        else:
            sources.write_text('deb https://deb.debian.org/debian bullseye main\n'
                               'deb https://deb.debian.org/debian bullseye-updates main\n'
                               'deb https://security.debian.org/debian-security bullseye-security main\n')
            options = ['-o', 'Dir::Etc::sourcelist=' + str(sources), '-o', 'Dir::Etc::sourceparts=-']
            run('sudo', 'apt-get', *options, 'update')
        run('sudo', 'apt-get', *options, 'install', '-y', 'build-essential', 'libncurses-dev',
            'libffi-dev', 'libgpiod-dev', 'python3-dev', 'pkg-config')
    run('sudo', 'systemctl', 'stop', 'klipper')
    run('sudo', 'systemctl', 'stop', 'klipper-mcu')
    pending.write_text('Linux MCU build and installation required\n')
    if changes and update_host:
        run('git', '-C', str(folder), 'stash', 'push', '-m', 'LUGOWARE upgrade backup', '--', 'klippy/extras/multi_pin.py')
    if update_host:
        run('git', '-C', str(folder), 'checkout', '--detach', BASELINE)
    shutil.copy2(backup / 'multi_pin.py', folder / 'klippy/extras/multi_pin.py')
    run(str(Path.home() / 'klippy-env/bin/python'), '-m', 'pip', 'install', '-r', str(folder / 'scripts/klippy-requirements.txt'))
    config = folder / '.config'
    if config.exists():
        shutil.copy2(config, backup / 'build.config')
    run('make', 'clean', cwd=folder)
    config.write_text('CONFIG_MACH_LINUX=y\n')
    run('make', 'olddefconfig', cwd=folder)
    if 'CONFIG_MACH_LINUX=y' not in config.read_text().splitlines():
        raise RuntimeError('Linux MCU configuration missing')
    run('make', '-j2', cwd=folder)
    run('make', 'flash', cwd=folder)
    run('sudo', 'systemctl', 'restart', 'klipper-mcu')
    run('systemctl', 'is-active', '--quiet', 'klipper-mcu')
    pending.unlink()
    # apply.sh starts Klipper after installing the extension and M5P firmware.
    print('[완료] Klipper 본체 및 CB2 MCU 업데이트', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    upgrade(Path(os.environ.get('KLIPPER_DIR', str(Path.home() / 'klipper'))),
            Path(os.environ['BACKUP_DIR']) / 'klipper-upgrade', args.check)
