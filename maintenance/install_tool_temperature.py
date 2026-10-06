"""Install the tested tool-temperature extension and print-menu integration."""
import argparse
import os
from pathlib import Path
import re
import shutil


def job_patch(text):
    old = '{"panel": "temperature", "extra": extruder}'
    new = '{"panel": "tool_temperature"}'
    if old not in text and new not in text:
        raise ValueError('Unsupported job_status.py: nozzle button not found')
    text = text.replace(old, new)
    # Keep other auxiliary heaters on the stock temperature panel.
    bed = '{"panel": "tool_temperature" if dev == "heater_bed" else "temperature", "extra": dev}'
    return text.replace('{"panel": "temperature", "extra": dev}', bed)


def menu_patch(text):
    for name in ('temperature', 'camera', 'pins'):
        header = '[menu __print ' + name + ']'
        pattern = re.compile(r'^' + re.escape(header) + r'[^\n]*\n(?:(?!^\[|^#~#).*(?:\n|$))*', re.M)
        match = pattern.search(text)
        if match:
            section = match.group()
            section = re.sub(r'^\s*enable\s*[:=].*$', 'enable: False', section, flags=re.M) if re.search(r'^\s*enable\s*[:=]', section, re.M) else section.rstrip() + '\nenable: False\n'
            text = text[:match.start()] + section + text[match.end():]
        else:
            text = header + '\nenable: False\n\n' + text
    return text


def install(config, screen, klipper, backup, config_only=False):
    changes = {config / 'KlipperScreen.conf': menu_patch((config / 'KlipperScreen.conf').read_text(encoding='utf-8'))}
    if not config_only:
        source = Path(__file__).with_name('lugo_tool_temperature.py').read_text(encoding='utf-8')
        compile(source, 'lugo_tool_temperature.py', 'exec')
        job = screen / 'panels/job_status.py'
        updated = job_patch(job.read_text(encoding='utf-8'))
        compile(updated, str(job), 'exec')
        cfg = config / 'printer.cfg'
        content = cfg.read_text(encoding='utf-8')
        if not re.search(r'^\[lugo_tool_temperature\]\s*$', content, re.M):
            content = '[lugo_tool_temperature]\n\n' + content
        changes.update({klipper / 'klippy/extras/lugo_tool_temperature.py': source, job: updated, cfg: content})
    # Validate all inputs before the first mutation; retain previous versions.
    for path, text in changes.items():
        if path.exists() and path.read_text(encoding='utf-8') == text:
            continue
        backup.mkdir(parents=True, exist_ok=True)
        saved = backup / path.name
        if path.exists() and not saved.exists():
            shutil.copy2(path, saved)
        path.write_text(text, encoding='utf-8')
    print('[확인 완료] 툴별 출력 온도 / 출력 메뉴 설정')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config-only', action='store_true')
    args = parser.parse_args()
    home = Path.home()
    install(home / 'printer_data/config', Path(os.environ.get('KLIPPERSCREEN_DIR', home / 'KlipperScreen')),
            Path(os.environ.get('KLIPPER_DIR', home / 'klipper')),
            Path(os.environ.get('BACKUP_DIR', home / 'lugoware_backups/tool-temperature-menu')) / 'tool-temperature', args.config_only)
