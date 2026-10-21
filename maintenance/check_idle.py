"""Verify idle state and stop preheating before maintenance."""
import json
import urllib.parse
import urllib.request


def request(path):
    with urllib.request.urlopen('http://127.0.0.1:7125' + path, timeout=10) as response:
        return json.load(response)['result']


def recover_stopped(previous=None):
    """Start, never restart, a service stopped by a failed installer."""
    from pathlib import Path
    import subprocess
    import time
    folder = Path.home()/'.local/share/lugoware'
    marker = folder/'maintenance-stopped.json'
    evidence = marker.is_file()
    for name in ('system-status.json', 'config-status.json'):
        try:
            data = previous if previous is not None and name == 'system-status.json' else json.loads((folder/name).read_text())
            evidence = evidence or data.get('state') == 'failed'
        except (OSError, ValueError, TypeError):
            pass
    if not evidence:
        return
    state = subprocess.check_output(['systemctl','show','klipper','-p','ActiveState','--value'], text=True).strip()
    if state not in ('inactive', 'failed'):
        return
    print('[복구] 이전 설치 중단으로 정지된 Klipper 서비스를 시작합니다.', flush=True)
    subprocess.run(['sudo','systemctl','start','moonraker'], check=True)
    subprocess.run(['sudo','systemctl','start','klipper'], check=True)
    for attempt in range(30):
        try:
            info = request('/printer/info')
            if info.get('state') in ('ready','error','shutdown'):
                print('[복구 확인] Klipper 연결 복원. 설치 전 상태를 다시 검사합니다.', flush=True)
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError('Klipper 자동 복구 후 연결 실패. klippy.log를 확인하세요.')


def main(previous=None):
    try:
        recover_stopped(previous)
        info = request('/printer/info')
        if info['state'] in ('error', 'shutdown'):
            return
        if info['state'] != 'ready':
            raise RuntimeError('Klipper is not ready; retry after startup')
        status = request('/printer/objects/query?print_stats&heaters')['status']
        if status['print_stats']['state'] not in ('standby', 'complete', 'cancelled', 'error'):
            raise RuntimeError('Printing or paused: finish/cancel the print first')
        for heater in status['heaters']['available_heaters']:
            query = urllib.parse.quote(heater, safe='')
            result = request('/printer/objects/query?' + query)['status'][heater]
            if result['target'] > 0:
                print('[진행] 업데이트 전 예열 중단: 모든 히터 목표 온도를 0으로 설정', flush=True)
                command = urllib.request.Request(
                    'http://127.0.0.1:7125/printer/gcode/script',
                    data=json.dumps({'script': 'TURN_OFF_HEATERS'}).encode(),
                    headers={'Content-Type': 'application/json'}, method='POST')
                with urllib.request.urlopen(command, timeout=10) as response:
                    json.load(response)
                verified = request('/printer/objects/query?print_stats&heaters')['status']
                if verified['print_stats']['state'] not in ('standby', 'complete', 'cancelled', 'error'):
                    raise RuntimeError('Print state changed during maintenance preparation')
                for name in verified['heaters']['available_heaters']:
                    encoded = urllib.parse.quote(name, safe='')
                    checked = request('/printer/objects/query?' + encoded)['status'][name]
                    if checked['target'] != 0:
                        raise RuntimeError('Heater target did not turn off: ' + name)
                print('[확인 완료] 예열 중단 확인. 업데이트를 계속합니다.', flush=True)
                break
    except Exception as exc:
        raise SystemExit('유휴 상태를 확인하지 못해 적용을 중단합니다: ' + str(exc))


if __name__ == '__main__':
    main()
