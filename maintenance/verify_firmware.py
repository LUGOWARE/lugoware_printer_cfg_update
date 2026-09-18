"""Validate the supplied M5P USB firmware before stopping services."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib


def inspect(data):
    if not 1024 <= len(data) <= 512 * 1024:
        raise ValueError('Unexpected firmware size')
    stack, reset = struct.unpack('<II', data[:8])
    if not (0x20000000 < stack <= 0x20024000 and reset & 1
            and 0x08002000 <= reset < 0x08002000 + len(data)):
        raise ValueError('Not an M5P image with an 8 KiB bootloader offset')
    for index, value in enumerate(data):
        if value != 0x78:
            continue
        try:
            identity = json.loads(zlib.decompress(data[index:]))
        except (ValueError, zlib.error, UnicodeError):
            continue
        config = identity.get('config', {})
        if config.get('MCU') == 'stm32g0b1xx' and config.get('RESERVE_PINS_USB') == 'PA11,PA12':
            return identity
    raise ValueError('M5P STM32G0B1 USB identity not found')


def main():
    folder = Path(sys.argv[1])
    data = (folder / 'firmware.bin').read_bytes()
    expected = (folder / 'firmware.sha256').read_text().split()[0]
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit('Firmware checksum mismatch')
    identity = inspect(data)
    print('M5P firmware: ' + identity['version'])


if __name__ == '__main__':
    main()
