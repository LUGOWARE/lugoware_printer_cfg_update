"""Keep the six-hour schedule, deferring restart while printing or paused."""
import fcntl
import json
import subprocess
import time
import urllib.request
from pathlib import Path


def idle():
    try:
        with urllib.request.urlopen('http://127.0.0.1:7125/printer/objects/query?print_stats&idle_timeout', timeout=3) as r:
            status = json.load(r)['result']['status']
        return (status['print_stats']['state'] in ('standby', 'complete', 'cancelled', 'error')
                and status['idle_timeout']['state'] in ('Idle', 'Ready'))
    except Exception:
        return False


def main():
    root = Path('/run/lugoware-screen-restart')
    root.mkdir(mode=0o755, exist_ok=True)
    with (root/'lugoware-screen-restart.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        notice = root/'notice.json'
        try:
            while True:
                while not idle():
                    time.sleep(5)
                deadline = time.time() + 60
                temp = notice.with_suffix('.tmp')
                temp.write_text(json.dumps({'deadline': deadline}))
                temp.replace(notice)
                while time.time() < deadline:
                    if not idle():
                        notice.unlink(missing_ok=True)
                        break
                    time.sleep(min(1, max(0, deadline-time.time())))
                else:
                    if idle():
                        subprocess.run(['/usr/bin/systemctl', 'restart', 'KlipperScreen'], check=True)
                        return
        finally:
            notice.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
