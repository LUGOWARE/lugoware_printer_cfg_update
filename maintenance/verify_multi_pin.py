import hashlib
from pathlib import Path
import sys
import time
from check_idle import request


def verify(folder, source, query=request):
    target = folder / 'klippy/extras/multi_pin.py'
    if target.read_bytes() != source.read_bytes():
        raise RuntimeError('multi_pin.py was replaced after installation: ' + str(target))
    info = query('/printer/info')
    if info.get('state') != 'ready':
        raise RuntimeError(info.get('state_message', 'Klipper not ready'))
    running_path = info.get('klipper_path')
    if running_path and Path(running_path).resolve() != folder.resolve():
        raise RuntimeError('Klipper is running from a different directory: ' + running_path)
    commands = query('/printer/gcode/help')
    if 'SET_MULTI_PIN_MODE' not in commands:
        raise RuntimeError('SET_MULTI_PIN_MODE is not registered in running Klipper')
    print('Extension verified: file SHA256=' + hashlib.sha256(target.read_bytes()).hexdigest())
    print('Runtime command verified: SET_MULTI_PIN_MODE')


if __name__ == '__main__':
    for attempt in range(30):
        try:
            verify(Path(sys.argv[1]), Path(__file__).with_name('multi_pin.py'))
            break
        except Exception as exc:
            last = str(exc)
            time.sleep(2)
    else:
        raise SystemExit(last)
