import time
import sys
from pathlib import Path
from check_idle import request
from verify_firmware import inspect

expected = inspect(Path(sys.argv[1]).read_bytes())['version']

last = 'No response'
for attempt in range(30):
    try:
        info = request('/printer/info')
        if info.get('state') == 'ready':
            status = request('/printer/objects/query?mcu')['status']['mcu']
            actual = status.get('mcu_version')
            if actual == expected:
                print('Klipper READY: MCU 연결 및 펌웨어 버전 검증 완료')
                break
            last = 'MCU version mismatch: expected %s, got %s' % (expected, actual)
        else:
            last = info.get('state_message', info.get('state', 'unknown'))
    except Exception as exc:
        last = str(exc)
    time.sleep(2)
else:
    raise SystemExit('업로드 후 Klipper READY 확인 실패: ' + last)
