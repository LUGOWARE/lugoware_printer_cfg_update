import time
from check_idle import request

last = 'No response'
for attempt in range(30):
    try:
        info = request('/printer/info')
        if info.get('state') == 'ready':
            print('Klipper READY: MCU 연결 및 설정 로드 완료')
            break
        last = info.get('state_message', info.get('state', 'unknown'))
    except Exception as exc:
        last = str(exc)
    time.sleep(2)
else:
    raise SystemExit('업로드 후 Klipper READY 확인 실패: ' + last)
