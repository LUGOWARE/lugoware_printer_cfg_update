"""Decide from the live MCU, never from a cached install marker."""
from pathlib import Path
import sys
from check_idle import request
from verify_firmware import inspect
from upgrade_klipper import release


def decide(info, status, expected):
    if info.get('state') == 'ready':
        actual = status.get('mcu', {}).get('mcu_version')
        if actual == expected:
            return 'skip'
        # Preserve a working different firmware on an already compatible host.
        if actual and release(info.get('software_version', '')) >= (0, 13, 0):
            return 'keep'
    return 'flash'


if __name__ == '__main__':
    info = request('/printer/info')
    status = request('/printer/objects/query?mcu')['status'] if info.get('state') == 'ready' else {}
    expected = inspect(Path(sys.argv[1]).read_bytes())['version']
    print(decide(info, status, expected))
