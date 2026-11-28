import hashlib
import json
from pathlib import Path
import sys
import time
from check_idle import request


def verify(folder, source, query=request, profile=None):
    target = folder / 'klippy/extras/multi_pin.py'
    if target.read_bytes() != source.read_bytes():
        raise RuntimeError('multi_pin.py was replaced after installation: ' + str(target))
    info = query('/printer/info')
    if info.get('state') != 'ready':
        raise RuntimeError(info.get('state_message', 'Klipper not ready'))
    running_path = info.get('klipper_path')
    if running_path and Path(running_path).resolve() != folder.resolve():
        raise RuntimeError('Klipper is running from a different directory: ' + running_path)
    if profile == 'toolhead_single':
        status = query('/printer/objects/query?configfile&lugo_diagnostics')['status']
        settings = status['configfile']['settings']
        if (settings.get('extruder', {}).get('heater_pin') != 'PC5'
                or settings.get('heater_generic toolhead', {}).get('heater_pin') != 'PA7'
                or 'multi_pin dual_hotend_heater' in settings):
            raise RuntimeError('Single-nozzle profile requires PC5 nozzle and PA7 auxiliary heater')
        if 'lugo_diagnostics' not in status:
            raise RuntimeError('LUGOWARE diagnostics are not active')
        print('Runtime heater profile verified: PC5 nozzle, PA7 auxiliary heater')
        return
    commands = query('/printer/gcode/help')
    if 'SET_MULTI_PIN_MODE' not in commands:
        raise RuntimeError('SET_MULTI_PIN_MODE is not registered in running Klipper')
    print('Extension verified: file SHA256=' + hashlib.sha256(target.read_bytes()).hexdigest())
    print('Runtime command verified: SET_MULTI_PIN_MODE')


if __name__ == '__main__':
    marker = Path.home() / '.local/share/lugoware/variant.json'
    profile = json.loads(marker.read_text())['variant'] if marker.is_file() else None
    for attempt in range(30):
        try:
            verify(Path(sys.argv[1]), Path(__file__).with_name('multi_pin.py'), profile=profile)
            break
        except Exception as exc:
            last = str(exc)
            time.sleep(2)
    else:
        raise SystemExit(last)
