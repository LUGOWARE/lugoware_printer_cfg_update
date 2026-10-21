"""Install tested touch controls without replacing board-specific configuration."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import re
from patch_print_controls import feature_macros
from october_features import job, notification, popup


def patch_ui(source, name):
    if name == "job_status.py":
        source = job(source, reverse=True)
    upgrades = json.loads(Path(__file__).with_name('print_features').joinpath('preprint_patches.json').read_text(encoding='utf-8')).get(name, [])
    # Normalize an already upgraded panel before applying the base migration.
    for old, new in reversed(upgrades):
        if new in source:
            source = source.replace(new, old, 1)
    patches = json.loads(Path(__file__).with_name('print_features').joinpath('ui_patches.json').read_text(encoding='utf-8'))
    for old, new in patches[name]:
        if new in source:
            continue
        if source.count(old) != 1:
            raise ValueError('Unsupported print UI source: ' + name + '\n' + old[:180])
        source = source.replace(old, new, 1)
    for old, new in upgrades:
        if new in source:
            continue
        if source.count(old) != 1:
            raise ValueError('Unsupported preprint UI source: ' + name + '\n' + old[:180])
        source = source.replace(old, new, 1)
    if name == "job_status.py":
        source = job(source)
    if name == "screen.py":
        source = popup(source)
    compile(source, name, 'exec')
    return source


def install(home, screen, klipper, backup):
    assets = Path(__file__).with_name('print_features')
    config = home / 'printer_data/config'
    changes = {}
    for name, relative in [('job_status.py', 'panels/job_status.py'), ('gcodes.py', 'panels/gcodes.py'),
                           ('screen_panel.py', 'ks_includes/screen_panel.py'), ('screen.py', 'screen.py')]:
        path = screen / relative
        changes[path] = patch_ui(path.read_text(encoding='utf-8'), name)
    handler = screen / 'ks_includes/notification_handler.py'
    changes[handler] = notification(handler.read_text(encoding='utf-8'))
    changes[klipper / 'klippy/extras/probe_auto_recovery.py'] = (assets / 'probe_auto_recovery.py').read_text(encoding='utf-8')
    for name in ('print_controls.py', 'toolchange_count.py', 'restart_notice.py', 'info_marquee.py'):
        changes[screen / 'ks_includes' / name] = (assets / name).read_text(encoding='utf-8')
    changes[klipper / 'klippy/extras/print_sensor.py'] = (assets / 'print_sensor.py').read_text(encoding='utf-8')
    for images in (screen / 'styles').glob('*/images'):
        changes[images / 'toolchanger-requested.svg'] = (assets / 'toolchanger-requested.svg').read_text(encoding='utf-8')
    p = config / 'printer.cfg'
    text = p.read_text(encoding='utf-8')
    if '[print_sensor]' not in text:
        text = text.replace('[fast_cancel]', '[fast_cancel]\n[print_sensor]', 1)
    if '[print_sensor]' not in text:
        raise ValueError('Missing fast_cancel section')
    if '[probe_auto_recovery]' not in text:
        text = text.replace('[print_sensor]', '[print_sensor]\n\n[probe_auto_recovery]\nattempts: 2\nminimum_clearance: 1.0', 1)
    changes[p] = text
    if os.environ.get('LUGOWARE_SYSTEM_ONLY') != '1':
        p = config / 'printer_base.cfg'
        changes[p] = feature_macros(p.read_text(encoding='utf-8'))
    for p, text in changes.items():
        if p.suffix == '.py':
            compile(text, str(p), 'exec')
    for p, text in changes.items():
        if p.exists() and p.read_text(encoding='utf-8') == text:
            continue
        saved = backup / p.relative_to(home)
        saved.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and not saved.exists():
            shutil.copy2(p, saved)
        p.write_text(text, encoding='utf-8')
    cron = subprocess.run(['crontab', '-l'], capture_output=True, text=True, env={**os.environ, 'LC_ALL': 'C'})
    if cron.returncode == 0 and Path('/opt/lugoware/screen-restart/schedule.py').is_file():
        lines = cron.stdout.splitlines()
        kept = [line for line in lines if not re.fullmatch(
            r'\s*(?:0 \*/6|59 5,11,17,23) \* \* \* ' + re.escape(str(home / 'klipperscreen_restart.sh')) + r'\s*', line)]
        if kept != lines:
            backup.mkdir(parents=True, exist_ok=True)
            saved = backup / 'user-crontab.txt'
            if not saved.exists():
                saved.write_text(cron.stdout)
            subprocess.run(['crontab', '-'], input='\n'.join(kept)+'\n', text=True, check=True)
    elif cron.returncode != 0 and 'no crontab for' not in cron.stderr:
        raise RuntimeError('Cannot read user crontab; restart schedule migration stopped')
    print('Installed toolchange counts, touch lock, filament policy and print UI.')


if __name__ == '__main__':
    home = Path.home()
    install(home, Path(os.environ.get('KLIPPERSCREEN_DIR', home / 'KlipperScreen')),
            Path(os.environ.get('KLIPPER_DIR', home / 'klipper')),
            Path(os.environ['BACKUP_DIR']) / 'print-features')
