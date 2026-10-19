"""Install tested touch controls without replacing board-specific configuration."""
import json
import os
from pathlib import Path
import shutil
from patch_print_controls import feature_macros


def patch_ui(source, name):
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
    for name in ('print_controls.py', 'toolchange_count.py'):
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
    print('Installed toolchange counts, touch lock, filament policy and print UI.')


if __name__ == '__main__':
    home = Path.home()
    install(home, Path(os.environ.get('KLIPPERSCREEN_DIR', home / 'KlipperScreen')),
            Path(os.environ.get('KLIPPER_DIR', home / 'klipper')),
            Path(os.environ['BACKUP_DIR']) / 'print-features')
