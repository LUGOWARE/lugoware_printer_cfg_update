"""Register two standard Git updaters and detached, non-overlapping worker services."""
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys

URL = 'https://github.com/LUGOWARE/lugoware_printer_cfg_update.git'


def configuration(text, branch):
    if branch not in ('FLEX4_M', 'FLEX4_L', 'FLEX4_W'):
        raise ValueError('Invalid model')
    for name in ('lugoware_config', 'lugoware_system', 'lugoware_updates'):
        section = name if name == 'lugoware_updates' else 'update_manager ' + name
        text = re.sub(r'(?ms)^\[' + re.escape(section) + r'\][^\n]*\n.*?(?=^\[|\Z)', '', text)
    for name, primary in (('lugoware_config', branch), ('lugoware_system', 'main')):
        text = text.rstrip() + f'''

[update_manager {name}]
type: git_repo
path: ~/{name}
origin: {URL}
primary_branch: {primary}
is_system_service: True
managed_services: {name}
'''
    return text.rstrip() + '\n\n[lugoware_updates]\n'


def service_units(user, home, channel):
    # The short trigger is safe to restart even during an active installation.
    # systemctl start leaves an already-running worker alone.
    worker = f'lugoware-{channel}-worker'
    trigger = f'''[Unit]
Description=LUGOWARE {channel} update trigger
[Service]
Type=oneshot
ExecStart=/bin/systemctl start --no-block {worker}.service
'''
    unit = f'''[Unit]
Description=LUGOWARE {channel} installer
After=network-online.target
[Service]
Type=simple
User={user}
Environment=HOME={home}
Environment=PYTHONUNBUFFERED=1
WorkingDirectory={home}
ExecStart=/usr/bin/python3 {home}/.local/share/lugoware/channel_worker.py {channel}
Restart=no
TimeoutStopSec=30
'''
    return {f'lugoware_{channel}.service': trigger, worker + '.service': unit}


def install(branch):
    home = Path.home()
    user = pwd.getpwuid(os.getuid()).pw_name
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', user) or str(home) != '/home/' + user:
        raise ValueError('Expected a standard /home/user installation')
    # Background installers cannot use an interactive sudo password prompt.
    # Verify existing privileges, never grant broad new sudo access.
    subprocess.run(['sudo', '-n', '-k', 'true'], check=True)
    source = Path(__file__).resolve().parent
    cache = home / '.local/share/lugoware'
    cache.mkdir(parents=True, exist_ok=True)
    backup = Path(os.environ['BACKUP_DIR']) / 'update-channels'
    backup.mkdir(parents=True, exist_ok=True)
    system_repo = home / 'lugoware_system'
    if not system_repo.exists():
        subprocess.run(['git', 'clone', '--branch', 'main', URL, str(system_repo)], check=True)
    origin = subprocess.check_output(['git', '-C', str(system_repo), 'remote', 'get-url', 'origin'], text=True).strip()
    if origin not in (URL, URL[:-4]):
        raise ValueError('Unexpected lugoware_system origin; preserved without modification')
    branch_now = subprocess.check_output(['git', '-C', str(system_repo), 'branch', '--show-current'], text=True).strip()
    if branch_now != 'main':
        raise ValueError('lugoware_system must track main; existing checkout preserved')
    for channel in ('config', 'system'):
        # Retire old post-merge hooks, which copied more than the requested files.
        hook = home / ('lugoware_' + channel) / '.git/hooks/post-merge'
        if hook.exists():
            if 'Config files updated from repo.' not in hook.read_text():
                raise ValueError('Unknown post-merge hook; inspect before replacing: ' + str(hook))
            shutil.copy2(hook, backup / (channel + '-post-merge'))
            hook.unlink()
    # Copy dependencies as well so future jobs use the last successfully installed code.
    for path in source.glob('*.py'):
        shutil.copy2(path, cache / path.name)
    for channel in ('config', 'system'):
        for name, content in service_units(user, home, channel).items():
            temporary = backup / name
            temporary.write_text(content)
            subprocess.run(['sudo', '-n', 'install', '-m', '644', str(temporary),
                            '/etc/systemd/system/' + name], check=True)
    subprocess.run(['sudo', '-n', 'systemctl', 'daemon-reload'], check=True)
    allow = home / 'printer_data/moonraker.asvc'
    old = allow.read_text()
    shutil.copy2(allow, backup / allow.name)
    for name in ('lugoware_config', 'lugoware_system'):
        if name not in old.splitlines():
            old = old.rstrip() + '\n' + name + '\n'
    allow.write_text(old)
    component = home / 'moonraker/moonraker/components/lugoware_updates.py'
    if component.exists():
        shutil.copy2(component, backup / component.name)
    shutil.copy2(source / 'lugoware_updates.py', component)
    cfg = home / 'printer_data/config/moonraker.conf'
    updated = configuration(cfg.read_text(), branch)
    shutil.copy2(cfg, backup / cfg.name)
    cfg.write_text(updated)
    print('Registered lugoware_config / lugoware_system. Installation results appear in announcements.')


if __name__ == '__main__':
    install(sys.argv[1])
