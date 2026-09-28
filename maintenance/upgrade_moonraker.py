"""Bring old Moonraker installations to v0.11.0 before applying patches."""
import os
from pathlib import Path
import shutil
import subprocess
import time

from upgrade_klipper import version_key
from update_components import api, restore_known_patch

BASELINE = '68db047aa9189248800904531f6354d8fd76d8eb'
MIN_VERSION = (0, 11, 0, 0)


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def run(*args):
    subprocess.run(args, check=True)


def wait_server():
    last = 'Moonraker unavailable'
    for _ in range(90):
        try:
            info = api('/server/info')
            if version_key(info['moonraker_version']) >= MIN_VERSION:
                return
            last = 'Running Moonraker version: ' + info['moonraker_version']
        except Exception as exc:
            last = str(exc)
        time.sleep(2)
    raise RuntimeError(last)


def upgrade(folder, backup):
    version = output('git', '-C', str(folder), 'describe', '--tags', '--long', '--dirty')
    pending = Path(output('git', '-C', str(folder), 'rev-parse', '--absolute-git-dir')) / 'lugoware-moonraker-pending'
    old = version_key(version) < MIN_VERSION
    if not old and not pending.exists():
        print('[건너뜀] Moonraker: ' + version, flush=True)
        # The process must also use this source version before dependent updates.
        run('sudo', 'systemctl', 'restart', 'moonraker')
        wait_server()
        return
    backup.mkdir(parents=True, exist_ok=True)
    if old:
        changes = output('git', '-C', str(folder), 'diff', 'HEAD', '--name-only').splitlines()
        known = 'moonraker/components/update_manager/update_manager.py'
        if set(changes) - {known}:
            raise RuntimeError('Unknown Moonraker edits preserved: ' + ', '.join(changes))
        (backup / 'commit.txt').write_text(output('git', '-C', str(folder), 'rev-parse', 'HEAD'))
        shutil.copytree(folder, backup / 'source', ignore=shutil.ignore_patterns('.git', '__pycache__'), dirs_exist_ok=True)
        shutil.copytree(Path.home() / 'printer_data/config', backup / 'config', dirs_exist_ok=True)
        if changes:
            restore_known_patch(folder, backup)
        print('[진행] Moonraker v0.11.0-0 다운로드', flush=True)
        run('git', '-C', str(folder), 'fetch', '--tags', 'https://github.com/Arksine/moonraker.git', BASELINE)
        if version_key(output('git', '-C', str(folder), 'describe', '--tags', '--long', BASELINE)) != MIN_VERSION:
            raise RuntimeError('Moonraker pinned version mismatch')
    run('sudo', 'systemctl', 'stop', 'moonraker')
    pending.write_text(BASELINE)
    if old:
        run('git', '-C', str(folder), 'checkout', '--detach', BASELINE)
    print('[진행] Moonraker 공식 의존성·서비스 설치', flush=True)
    run('bash', str(folder / 'scripts/install-moonraker.sh'))
    wait_server()
    pending.unlink()
    print('[확인 완료] Moonraker v0.11.0-0 이상 실행 확인', flush=True)


if __name__ == '__main__':
    upgrade(Path(os.environ.get('MOONRAKER_DIR', str(Path.home() / 'moonraker'))),
            Path(os.environ['BACKUP_DIR']) / 'moonraker-upgrade')
