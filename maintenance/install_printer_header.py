"""Standardize the printer header, preserving device connections and SAVE_CONFIG."""
import argparse
from pathlib import Path
import re
import shutil

SAVED = '#*# <---------------------- SAVE_CONFIG ---------------------->'


def sections(text):
    return {m[1]: m[0].rstrip() + '\n\n' for m in
            re.finditer(r'(?ms)^\[([^\]\n]+)\][^\n]*\n.*?(?=^\[|\Z)', text)}


def merge(existing, template, fallback='', gcode_path=None):
    body, marker, saved = existing.partition(SAVED)
    old = sections(fallback.partition(SAVED)[0])
    old.update(sections(body))
    mcu = old.get('mcu', '')
    if not re.search(r'(?m)^\s*(?:serial|canbus_uuid)\s*[:=]\s*\S+', mcu):
        raise ValueError('MCU connection missing; refusing to copy another printer address')
    result = template
    # Retain complete connection sections, including restart_method/baud/CAN.
    for name, block in old.items():
        if name == 'mcu' or name.startswith('mcu '):
            pattern = r'(?ms)^\[' + re.escape(name) + r'\][^\n]*\n.*?(?=^\[|\Z)'
            if re.search(pattern, result):
                result = re.sub(pattern, lambda m: block, result)
            else:
                result = result.rstrip() + '\n\n' + block
    sd = old.get('virtual_sdcard', '')
    path = re.search(r'(?m)^\s*path\s*[:=]\s*(.+?)\s*$', sd)
    result = result.replace('@GCODE_PATH@', path[1] if path else str(gcode_path or Path.home()/'printer_data/gcodes'))
    if '@MCU_SERIAL@' in result:
        raise ValueError('Unresolved MCU placeholder')
    return result.rstrip() + '\n\n' + marker + saved


def install(template, target, backup, fallback=None):
    previous = target.read_bytes().decode('utf-8')
    updated = merge(previous, template.read_text(encoding='utf-8'),
                    fallback.read_text(encoding='utf-8') if fallback and fallback.exists() else '')
    if updated == previous:
        return
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(target, backup)
    target.write_bytes(updated.encode('utf-8'))
    print('[완료] printer.cfg 공통 헤더 적용 / MCU 연결·SAVE_CONFIG 보존')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('template', type=Path)
    p.add_argument('target', type=Path)
    p.add_argument('backup', type=Path)
    p.add_argument('--fallback', type=Path)
    args = p.parse_args()
    install(args.template, args.target, args.backup, args.fallback)
