"""Stage-based UI progress. Git download completion is not installation success."""
import re
import json
import time
from pathlib import Path

class Progress:
    def __init__(self, cache_path=None):
        self.cache_path = (Path.home() / '.local/share/lugoware/screen-update-progress.json'
                           if cache_path is True else Path(cache_path) if cache_path else None)
        self.identity = None
        self.saved = None
        self.percent=0
        self.state='running'
        self.error=''
        self.lugoware=False

    def update(self, data):
        identity = (str(data.get('application', '')), str(data.get('proc_id', '')))
        valid = identity[0] in ('lugoware_system', 'lugoware_config', 'full') and identity[1] not in ('', 'None')
        if valid and identity != self.identity:
            self.identity = identity
            self.percent = 0
            self.state = 'running'
            self.error = ''
            self.lugoware = identity[0].startswith('lugoware_')
            self.saved = None
            if self.cache_path:
                try:
                    record = json.loads(self.cache_path.read_text(encoding='utf-8'))
                    if (record.get('identity') == list(identity) and
                            record.get('state') == 'running' and
                            0 <= time.time() - float(record['time']) < 86400):
                        self.percent = max(0, min(95, int(record['percent'])))
                except (OSError, ValueError, TypeError, KeyError):
                    pass
        state = self._update(data)
        if valid and self.cache_path:
            signature = (identity, self.percent, state)
            if signature != self.saved:
                try:
                    self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = self.cache_path.with_suffix('.tmp')
                    temporary.write_text(json.dumps(dict(identity=identity, percent=self.percent,
                                                        state=state, time=time.time())), encoding='utf-8')
                    temporary.replace(self.cache_path)
                    self.saved = signature
                except OSError:
                    pass
        return state

    def _update(self, data):
        message=str(data.get('message',''))
        lower=message.lower()
        app=str(data.get('application',''))
        self.lugoware=self.lugoware or 'lugoware_' in app or 'lugoware_' in lower
        complete=bool(data.get('complete'))
        if self.state!='running':
            return self.state
        failed=('설치 실패' in message or '업데이트 실패' in message or
                (complete and any(word in lower for word in ('error','failed','failure','실패'))))
        if failed:
            self.state='failed'
            self.error=message[:500]
            return self.state
        success=(complete and ('실제 설치 및 검증 완료' in message or not self.lugoware))
        if success:
            self.percent=100
            self.state='complete'
            return self.state
        percent=3
        if any(word in lower for word in ('fetch','download','receiving','unpacking','cloning')):
            percent=10
            match=re.search(r'(\d+)%',message)
            if match:percent=5+int(match[1])*20/100
        if '설치 대기' in message or '다운로드 완료' in message:
            percent=30
        if '설치 진행' in message:
            percent=35
        match=re.search(r'\[업데이트\s*(\d+)\s*/\s*(\d+)\]',message)
        if match and int(match[2]):
            percent=35+50*(int(match[1])-1)/int(match[2])
        if '[검증]' in message or 'READY 확인' in message:
            percent=max(percent,90)
        if '펌웨어 정책 검증' in message or 'Klipper READY' in message:
            percent=max(percent,95)
        self.percent=max(self.percent,min(95,int(percent)))
        return self.state
