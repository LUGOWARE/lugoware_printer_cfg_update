"""Read-only final check; never starts recovery or factory reset."""
import json
from pathlib import Path
import urllib.request

with urllib.request.urlopen('http://127.0.0.1:7125/printer/objects/query?lugo_recovery', timeout=10) as response:
    status = json.load(response)['result']['status']
if 'lugo_recovery' not in status:
    raise RuntimeError('Interrupted-print recovery extension is not loaded')
home = Path.home()
for relative in ('.local/share/lugoware/factory_reset.py', 'lugoware-factory-reset'):
    if not (home / relative).is_file():
        raise RuntimeError('Factory reset tool is missing: ' + relative)
print('[확인 완료] 중단 출력 복구 확장 및 출고 초기화 도구 설치 확인')
