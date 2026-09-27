import time
import sys
import urllib.request
from pathlib import Path
from check_idle import request
from verify_firmware import inspect

expected = None if sys.argv[1] == '--ready-only' else inspect(Path(sys.argv[1]).read_bytes())['version']

last = 'No response'
reset_sent = False
for attempt in range(30):
    try:
        info = request('/printer/info')
        if info.get('state') == 'ready':
            status = request('/printer/objects/query?mcu')['status']['mcu']
            actual = status.get('mcu_version')
            if actual and (expected is None or actual == expected):
                print('Klipper READY: MCU 연결 및 펌웨어 버전 검증 완료')
                break
            last = 'MCU version mismatch: expected %s, got %s' % (expected, actual)
        else:
            last = info.get('state_message', info.get('state', 'unknown'))
            if not reset_sent and 'oids already allocated' in last:
                urllib.request.urlopen(urllib.request.Request(
                    'http://127.0.0.1:7125/printer/firmware_restart', data=b'', method='POST'), timeout=10).close()
                reset_sent = True
    except Exception as exc:
        last = str(exc)
    time.sleep(2)
else:
    raise SystemExit('업로드 후 Klipper READY 확인 실패: ' + last)
