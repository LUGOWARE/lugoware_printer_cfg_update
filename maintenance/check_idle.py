"""Read local Moonraker state before a maintenance operation."""
import json
import urllib.parse
import urllib.request


def request(path):
    with urllib.request.urlopen('http://127.0.0.1:7125' + path, timeout=10) as response:
        return json.load(response)['result']


def main():
    try:
        info = request('/printer/info')
        if info['state'] in ('error', 'shutdown'):
            return
        if info['state'] != 'ready':
            raise RuntimeError('Klipper is not ready; retry after startup')
        status = request('/printer/objects/query?print_stats&heaters')['status']
        if status['print_stats']['state'] in ('printing', 'paused'):
            raise RuntimeError('Printing or paused: finish/cancel the print first')
        for heater in status['heaters']['available_heaters']:
            query = urllib.parse.quote(heater, safe='')
            result = request('/printer/objects/query?' + query)['status'][heater]
            if result['target'] > 0:
                raise RuntimeError('Turn off all heater targets before maintenance')
    except Exception as exc:
        raise SystemExit('유휴 상태를 확인하지 못해 적용을 중단합니다: ' + str(exc))


if __name__ == '__main__':
    main()
