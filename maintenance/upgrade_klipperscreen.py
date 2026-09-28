"""Upgrade KlipperScreen to a pinned minimum, before installing custom panels."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

from upgrade_klipper import version_key

BASELINE = '3f08a9f782f3232a205c8004f4c5a681637e2b42'
MIN_VERSION = (0, 4, 7, 191)


def run(*args):
    subprocess.run(args, check=True)


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def upgrade(folder, backup, venv, check=False):
    version = output('git', '-C', str(folder), 'describe', '--tags', '--long', '--dirty')
    pending = Path(output('git', '-C', str(folder), 'rev-parse', '--absolute-git-dir')) / 'lugoware-screen-pending'
    needs_update = version_key(version) < MIN_VERSION
    if not needs_update and not pending.exists():
        print('[건너뜀] KlipperScreen: ' + version, flush=True)
        return
    python = venv / 'bin/python'
    if not python.is_file():
        raise RuntimeError('KlipperScreen Python environment missing: ' + str(python))
    if check:
        print('[예정] KlipperScreen v0.4.7-191 업데이트 / 중단 작업 재개', flush=True)
        return
    backup.mkdir(parents=True, exist_ok=True)
    if needs_update:
        print('[진행] KlipperScreen 기존 소스·수정 파일 백업', flush=True)
        (backup / 'commit.txt').write_text(output('git', '-C', str(folder), 'rev-parse', 'HEAD'))
        shutil.copytree(folder, backup / 'source', ignore=shutil.ignore_patterns('.git', '__pycache__'), dirs_exist_ok=True)
        (backup / 'changes.patch').write_bytes(subprocess.check_output(
            ['git', '-C', str(folder), 'diff', '--binary', 'HEAD']))
        (backup / 'requirements-before.txt').write_text(output(str(python), '-m', 'pip', 'freeze'))
        print('[진행] KlipperScreen v0.4.7-191 공식 커밋 다운로드', flush=True)
        run('git', '-C', str(folder), 'fetch', '--tags', 'https://github.com/KlipperScreen/KlipperScreen.git', BASELINE)
        pinned = output('git', '-C', str(folder), 'describe', '--tags', '--long', BASELINE)
        if version_key(pinned) != MIN_VERSION:
            raise RuntimeError('Pinned KlipperScreen version mismatch: ' + pinned)
    run('sudo', 'systemctl', 'stop', 'KlipperScreen')
    pending.write_text(BASELINE)
    if needs_update:
        # Keep a Git recovery copy as well. Untracked custom assets remain in place.
        # checkout refuses untracked collisions instead of overwriting them.
        run('git', '-C', str(folder), 'stash', 'push', '-m', 'LUGOWARE before KlipperScreen v0.4.7-191')
        run('git', '-C', str(folder), 'checkout', '--detach', BASELINE)
    print('[진행] KlipperScreen Python 의존성 설치', flush=True)
    run(str(python), '-m', 'pip', 'install', '-r', str(folder / 'scripts/KlipperScreen-requirements.txt'))
    run(str(python), '-c', 'import gi, cairo, requests, websocket, jinja2, psutil, sdbus, sdbus_networkmanager; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk')
    pending.unlink()
    print('[확인 완료] KlipperScreen: ' + output('git', '-C', str(folder), 'describe', '--tags', '--long')
          + ' (사용자 패널·패치 적용 후 재시작)', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    upgrade(Path(os.environ.get('KLIPPERSCREEN_DIR', str(Path.home() / 'KlipperScreen'))),
            Path(os.environ['BACKUP_DIR']) / 'klipperscreen-upgrade',
            Path(os.environ.get('KLIPPERSCREEN_VENV', str(Path.home() / '.KlipperScreen-env'))), args.check)
