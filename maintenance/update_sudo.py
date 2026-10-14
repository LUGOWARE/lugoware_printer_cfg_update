#!/usr/bin/python3 -I
"""Translate known installer calls to fixed operations, never forward raw commands."""
import os
from pathlib import PurePosixPath
import sys


PACKAGES = ('fonts-noto-core', 'fonts-noto-cjk', 'build-essential', 'libncurses-dev', 'libffi-dev', 'libgpiod-dev', 'python3-dev', 'pkg-config', 'python3-virtualenv', 'libopenjp2-7', 'libsodium-dev', 'zlib1g-dev', 'libjpeg-dev', 'packagekit', 'wireless-tools', 'curl')

def translate(args):
    if args in (['-v'], ['-n', '-v']):
        return ['probe']
    if len(args) == 2 and args[0] == '--lugoware-prepare':
        return ['prepare', args[1]]
    if args == ['--lugoware-refresh-worker']:
        return ['refresh-worker']
    while args and args[0] in ('-n', '-k'):
        args = args[1:]
    if args == ['true']:
        return ['probe']
    if args == ['systemctl', 'restart', 'klipper', 'KlipperScreen']:
        return ['restart-printer']
    if len(args) == 3 and args[0] == 'systemctl' and args[1] in ('start', 'stop', 'restart') and args[2] in ('klipper', 'klipper-mcu', 'KlipperScreen', 'moonraker'):
        return ['service', args[1], args[2]]
    if args == ['systemctl', 'daemon-reload']:
        return ['reload-services']
    if len(args) == 3 and args[0] == 'python3' and PurePosixPath(args[1]).name == 'logo_guard.py' and args[2] in ('check', 'install', 'verify'):
        # The supplied script is never executed. The root policy uses its own fixed copy.
        return ['logo', args[2]]
    if args and args[0] == 'LC_ALL=C':
        args = args[1:]
    if args == ['crontab', '-l']:
        return ['cron-read']
    if len(args) == 2 and args[0] == 'crontab' and not args[1].startswith('-'):
        # No caller-provided crontab is read; the fixed scheduled task is ensured.
        return ['cron-ensure']
    if args == ['tee', '/etc/systemd/system/klipper.service.d/90-lugoware-extension.conf']:
        return ['extensions']
    if args == ['install', '-d', '-m', '755', '/opt/lugoware/multi-pin', '/etc/systemd/system/klipper.service.d']:
        return ['extensions']
    if len(args) == 6 and args[:3] == ['install', '-m', '644'] and args[-1] == '/opt/lugoware/multi-pin/' and [PurePosixPath(p).name for p in args[3:5]] == ['multi_pin.py', 'install_multi_pin.py']:
        return ['extensions']
    if args and args[0] == 'apt-get':
        rest = args[1:]
        # Only legacy source-list selectors are recognized. Their files/options
        # are not passed to root; root APT uses system-owned configuration.
        while len(rest) >= 2 and rest[0] == '-o' and rest[1].split('=', 1)[0] in ('Dir::Etc::sourcelist', 'Dir::Etc::sourceparts'):
            rest = rest[2:]
        if rest == ['update']:
            return ['packages']
        if rest and rest[0] == 'install' and all(x in PACKAGES or x in ('-y', '--no-install-recommends') for x in rest[1:]):
            # Root installs only its compiled-in package list, ignoring caller names.
            return ['packages']
    raise PermissionError('Unsupported privileged step; use the SSH installer for a new system migration')


if __name__ == '__main__':
    argv = ['/usr/bin/sudo', '-n', '/opt/lugoware/update-runtime/update_root.py'] + translate(sys.argv[1:])
    os.execv(argv[0], argv)
