#!/usr/bin/python3 -I
"""Root-owned bridge usable only inside the two root-defined updater services."""
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import fcntl

CONFIG = Path('/etc/lugoware-updates.json')
URL = 'https://github.com/LUGOWARE/lugoware_printer_cfg_update.git'
SAFE_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'


def authorized_channel(cgroup, caller_uid, expected_uid):
    if caller_uid != expected_uid:
        raise PermissionError('Wrong update service user')
    # An SSH session or user-created service cannot join these system cgroups.
    paths = [line.split(':', 2)[-1].rstrip('/') for line in cgroup.splitlines()]
    for channel in ('config', 'system'):
        if '/system.slice/lugoware-' + channel + '-worker.service' in paths:
            return channel
    raise PermissionError('Administrator access is restricted to LUGOWARE updater services')


def prepare(commit):
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Invalid commit')
    root = Path('/var/lib/lugoware-updates')
    root.mkdir(mode=0o755, parents=True, exist_ok=True)
    repo = root / 'official.git'
    env = {'PATH': SAFE_PATH, 'HOME': '/root', 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0'}
    if not repo.exists():
        subprocess.run(['/usr/bin/git', 'init', '--bare', str(repo)], env=env, check=True, stdout=sys.stderr)
    git = ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '--git-dir=' + str(repo)]
    subprocess.run(git + ['fetch', URL, 'main'], env=env, check=True, stdout=sys.stderr)
    subprocess.run(git + ['merge-base', '--is-ancestor', commit, 'FETCH_HEAD'], env=env, check=True)
    dest = root / commit
    if dest.exists():
        (root / "active-release").write_text(commit)
        return dest
    data = subprocess.check_output(git + ['archive', commit], env=env)
    pending = Path(tempfile.mkdtemp(prefix=commit + '.', dir=root))
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for entry in archive.getmembers():
            if entry.name.startswith('/') or '..' in Path(entry.name).parts or not (entry.isfile() or entry.isdir()):
                raise ValueError('Unsafe release archive member')
            target = pending / entry.name
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o755)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(entry).read())
                target.chmod(0o755 if entry.mode & 0o111 else 0o644)
    pending.chmod(0o755)
    pending.rename(dest)
    (root / "active-release").write_text(commit)
    return dest


RUNTIME = Path('/opt/lugoware/update-runtime')
STATE = Path('/var/lib/lugoware-updates')
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root', 'LANG': 'C.UTF-8',
       'LC_ALL': 'C', 'DEBIAN_FRONTEND': 'noninteractive'}
SERVICES = {'klipper', 'klipper-mcu', 'KlipperScreen', 'moonraker'}
PACKAGES = ('fonts-noto-core', 'fonts-noto-cjk', 'build-essential', 'libncurses-dev',
            'libffi-dev', 'libgpiod-dev', 'python3-dev', 'pkg-config', 'python3-virtualenv',
            'libopenjp2-7', 'libsodium-dev', 'zlib1g-dev', 'libjpeg-dev', 'packagekit',
            'wireless-tools', 'curl')
# These files run as the ordinary printer user, never imported by this root policy.
WORKER_FILES = ('channel_worker.py', 'run_worker.py', 'check_idle.py', 'install_screen_config.py',
                'patch_print_controls.py', 'final_print_ui.py', 'wait_ready.py', 'verify_firmware.py',
                'preserve_sensor_pins.py', 'october_features.py', 'stage_features.py', 'mesh_features.py')


def validate_action(args, channel):
    if args == ['probe'] or args == ['restart-printer']:
        return
    if channel != 'system':
        raise PermissionError('Config updates may only restart the printer services')
    if len(args) == 2 and args[0] == 'prepare' and re.fullmatch('[0-9a-f]{40}', args[1]):
        return
    if len(args) == 3 and args[0] == 'service' and args[1] in ('start', 'stop', 'restart') and args[2] in SERVICES:
        return
    if len(args) == 2 and args[0] == 'logo' and args[1] in ('check', 'install', 'verify'):
        return
    if args in ([name] for name in ('packages', 'extensions', 'cron-read', 'cron-ensure', 'refresh-worker', 'reload-services')):
        return
    raise PermissionError('Unsupported privileged operation; no command/path forwarding is allowed')


def trusted_dir(path):
    """Reject user-writable/symlink ancestors of all privileged destinations."""
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise PermissionError('Symlink in administrator path')
        info = parent.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise PermissionError('Administrator path is writable by another account')


def write_fixed(path, data, mode=0o644):
    # Paths are constants generated here, never caller input.
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    trusted_dir(path.parent)
    if path.is_symlink():
        raise PermissionError('Refusing symlink destination')
    fd, temporary = tempfile.mkstemp(prefix='.lugoware-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def active_source():
    trusted_dir(STATE)
    commit = (STATE / 'active-release').read_text().strip()
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise PermissionError('No verified active release')
    root = STATE / commit / 'maintenance'
    trusted_dir(root)
    return root


def run_fixed(argv, **kwargs):
    return subprocess.run(argv, env=ENV, cwd='/', check=True, **kwargs)


def execute(args, channel, cfg):
    validate_action(args, channel)
    action = args[0]
    if action == 'probe':
        return
    if action == 'restart-printer':
        run_fixed(['/usr/bin/systemctl', 'restart', 'klipper', 'KlipperScreen'])
    elif action == 'service':
        run_fixed(['/usr/bin/systemctl', args[1], args[2]])
    elif action == 'prepare':
        print(prepare(args[1]))
    elif action == 'reload-services':
        run_fixed(['/usr/bin/systemctl', 'daemon-reload'])
    elif action == 'packages':
        missing = []
        for package in PACKAGES:
            result = subprocess.run(['/usr/bin/dpkg-query', '-W', '-f=${Status}', package],
                                    env=ENV, cwd='/', capture_output=True, text=True)
            if result.returncode or result.stdout != 'install ok installed':
                missing.append(package)
        if missing:
            # Never accept APT options, package names or sources from the caller.
            run_fixed(['/usr/bin/apt-get', 'update'])
            run_fixed(['/usr/bin/apt-get', 'install', '-y', '--no-install-recommends', *missing])
    elif action == 'logo':
        # Fixed root-owned policy installed during the interactive bootstrap.
        run_fixed(['/usr/bin/python3', '-I', str(RUNTIME / 'logo_guard.py'), args[1]])
    elif action in ('cron-read', 'cron-ensure'):
        current = subprocess.run(['/usr/bin/crontab', '-l'], env=ENV, cwd='/', capture_output=True, text=True)
        if current.returncode and 'no crontab for' not in current.stderr:
            raise RuntimeError('Cannot read existing root crontab')
        if action == 'cron-read':
            sys.stdout.write(current.stdout)
        else:
            pattern = r'^\s*0\s+\*/6\s+\*\s+\*\s+\*\s+/(?:usr/)?bin/systemctl\s+restart\s+KlipperScreen(?:\.service)?\s*(?:#.*)?$'
            lines = [line for line in current.stdout.splitlines() if not re.match(pattern, line)]
            write_fixed(Path('/opt/lugoware/screen-restart/schedule.py'), (active_source() / 'screen_restart_schedule.py').read_bytes())
            lines = [line for line in lines if '/opt/lugoware/screen-restart/schedule.py' not in line]
            lines.append('59 5,11,17,23 * * * /usr/bin/python3 -I /opt/lugoware/screen-restart/schedule.py')
            run_fixed(['/usr/bin/crontab', '-'], input='\n'.join(lines) + '\n', text=True)
    elif action == 'extensions':
        source = active_source()
        unit_user = run_fixed(['/usr/bin/systemctl', 'show', '-p', 'User', '--value', 'klipper'],
                              capture_output=True, text=True).stdout.strip()
        if unit_user != cfg['user']:
            raise PermissionError('Klipper must run as the configured unprivileged printer user')
        for name in ('multi_pin.py', 'install_multi_pin.py'):
            write_fixed(Path('/opt/lugoware/multi-pin') / name, (source / name).read_bytes())
        user = cfg['user']
        if not re.fullmatch('[a-z_][a-z0-9_-]*', user):
            raise ValueError('Invalid configured user')
        dropin = '[Service]\nExecStartPre=/usr/bin/python3 /opt/lugoware/multi-pin/install_multi_pin.py "/home/' + user + '/klipper"\n'
        write_fixed(Path('/etc/systemd/system/klipper.service.d/90-lugoware-extension.conf'), dropin.encode())
        run_fixed(['/usr/bin/systemctl', 'daemon-reload'])
    elif action == 'refresh-worker':
        source = active_source()
        for name in WORKER_FILES:
            write_fixed(RUNTIME / name, (source / name).read_bytes())
        # Deliberately do not update this policy, sudoers, shim or service units.


def main():
    if os.geteuid() != 0:
        raise PermissionError('Use the registered sudo entry point')
    cfg = json.loads(CONFIG.read_text())
    channel = authorized_channel(Path('/proc/self/cgroup').read_text(),
                                 int(os.environ.get('SUDO_UID', '-1')), cfg['uid'])
    args = sys.argv[1:]
    validate_action(args, channel)
    os.umask(0o022)
    os.chdir('/')
    STATE.mkdir(mode=0o755, parents=True, exist_ok=True)
    trusted_dir(STATE)
    with (STATE / 'admin.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        execute(args, channel, cfg)


if __name__ == '__main__':
    main()

