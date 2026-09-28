"""Update only the requested installed components through Moonraker."""
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.error
import urllib.request

from check_idle import main as check_idle
from hide_klipper_updater import replacement, patch

COMPONENTS = ('mainsail', 'print_area_bed_mesh', 'sonar')


def api(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request('http://127.0.0.1:7125' + path, data=data,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=3600 if data is not None else 15) as response:
        result = json.load(response)
    if 'error' in result:
        raise RuntimeError(str(result['error']))
    return result['result']


def progress_request(label, path, body=None):
    # Requests are sent once; do not repeat an update after a lost response.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(api, path, body)
        while True:
            try:
                return future.result(timeout=15)
            except concurrent.futures.TimeoutError:
                if future.done():
                    return future.result()
                print('[진행 중] ' + label + ' — 응답 대기', flush=True)


def needs_update(name, info):
    if info.get('is_valid') is False or info.get('is_dirty') or info.get('corrupt'):
        raise RuntimeError(name + ': invalid or modified repository; no forced reset performed')
    if name == 'system':
        count = info.get('package_count')
        if not isinstance(count, int):
            raise RuntimeError('System package count unavailable')
        return count > 0
    current = info.get('current_hash') or info.get('version')
    remote = info.get('remote_hash') or info.get('remote_version')
    if not current or not remote or current == '?' or remote == '?':
        raise RuntimeError(name + ': version information unavailable')
    return current != remote


def wait_status():
    last = 'Moonraker unavailable'
    for _ in range(60):
        try:
            result = api('/machine/update/status')
            if not result.get('busy') and result.get('version_info'):
                return result
            last = 'Moonraker update still busy'
        except Exception as exc:
            last = str(exc)
        time.sleep(2)
    raise RuntimeError(last)


def refresh(name):
    for attempt in range(60):
        try:
            return progress_request(name, '/machine/update/refresh', {'name': name})
        except urllib.error.HTTPError as exc:
            if exc.code != 503 or attempt == 59:
                raise
            if attempt % 10 == 0:
                print('[대기] Moonraker 업데이트 관리자 초기화: ' + name, flush=True)
            time.sleep(2)


def restore_known_patch(folder, backup):
    relative = 'moonraker/components/update_manager/update_manager.py'
    path = folder / relative
    original = subprocess.check_output(['git', '-C', str(folder), 'show', 'HEAD:' + relative])
    current = path.read_bytes()
    if current == original:
        return path
    expected, _ = replacement(original.decode('utf-8'))
    if current != expected.encode('utf-8'):
        raise RuntimeError('Moonraker contains an unknown updater modification; retained without overwriting')
    shutil.copy2(path, backup / 'update_manager.before-update.py')
    path.write_bytes(original)
    return path


def main():
    backup = Path(os.environ['BACKUP_DIR']) / 'component-updates'
    backup.mkdir(parents=True, exist_ok=True)
    check_idle()
    for index, name in enumerate(COMPONENTS, 1):
        print(f'[추가 업데이트 {index}/{len(COMPONENTS)}] {name}: 최신 상태 조회', flush=True)
        status = wait_status()
        if name not in status['version_info']:
            print('[건너뜀] ' + name + ': 업데이트 관리자에 등록되지 않음', flush=True)
            continue
        status = refresh(name)
        before = status['version_info'][name]
        (backup / (name + '-before.json')).write_text(json.dumps(before, indent=2), encoding='utf-8')
        if not needs_update(name, before):
            print('[최신 상태] ' + name + ': ' + str(before.get('version', '0 packages')), flush=True)
            continue
        print('[업데이트] ' + name + ': ' + str(before.get('version', before.get('package_count'))) +
              ' → ' + str(before.get('remote_version', '최신 패키지')), flush=True)
        endpoint = '/machine/update/' + name if name in ('system', 'moonraker') else '/machine/update/client'
        body = {} if name in ('system', 'moonraker') else {'name': name}
        try:
            result = progress_request(name, endpoint, body)
            if result != 'ok':
                raise RuntimeError(name + ': unexpected update response ' + str(result))
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            # Moonraker can restart before its response reaches this client.
            if name != 'moonraker':
                raise
            print('[확인] Moonraker 재연결 후 업데이트 결과 확인: ' + str(exc), flush=True)
        wait_status()
        after = refresh(name)['version_info'][name]
        (backup / (name + '-after.json')).write_text(json.dumps(after, indent=2), encoding='utf-8')
        if needs_update(name, after):
            raise RuntimeError(name + ': updates remain after installation; inspect moonraker.log')
        print('[완료] ' + name + ': ' + str(after.get('version', '패키지 최신 상태')), flush=True)
    wait_status()
    if Path('/var/run/reboot-required').exists():
        print('[안내] 시스템 패키지가 재부팅을 요구합니다. 자동 재부팅하지 않습니다.', flush=True)


if __name__ == '__main__':
    main()
