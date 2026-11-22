"""Install tested touch controls without replacing board-specific configuration."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import re
from patch_print_controls import feature_macros
from home_lighting import home_panel
from october_features import job, notification, popup
from final_print_ui import once, status_layout
from paused_tool_service_hooks import SUBSCRIPTION, add_subscription


def patch_ui(source, name):
    dock_edits = []
    if name == 'job_status.py':
        from install_toolhead_variant import patch_ui as variant_ui
        path = Path(__file__).with_name('toolhead_variant') / 'ui_patches.json'
        edits = json.loads(path.read_text(encoding='utf-8'))['KlipperScreen/panels/job_status.py']
        dock_edits = [(old, new) for old, new in edits if new in source]
        if dock_edits:
            source = variant_ui(source, dock_edits, 'standard')
    had_paused_tools = name == 'screen.py' and SUBSCRIPTION in source
    if had_paused_tools:
        source = source.replace(SUBSCRIPTION, '')
    if name == "job_status.py":
        source = status_layout(source, reverse=True)
    # Temporarily remove the additive subscription for legacy block matching.
    # Restore it after migration; never discard the preanalysis status hook.
    preanalysis_line = '                "lugo_preanalysis": None,\n'
    had_preanalysis = name == 'screen.py' and preanalysis_line in source
    if had_preanalysis:
        if source.count(preanalysis_line) != 1:
            raise ValueError('Duplicate preanalysis subscription')
        source = source.replace(preanalysis_line, '', 1)
    # Normalize additive recovery hooks before older whole-method UI migrations.
    recovery_assets = Path(__file__).with_name('recovery')
    recovery_patches = json.loads((recovery_assets / 'ui_patches.json').read_text(encoding='utf-8')).get(name, [])
    had_recovery = any(new in source for old, new in recovery_patches)
    if had_recovery:
        for old, new in reversed(recovery_patches):
            source = source.replace(new, old)
    from followup_features import ui
    source = ui(source, name, reverse=True)
    if name == "gcodes.py":
        trials = json.loads(Path(__file__).with_name('print_features').joinpath('mesh_trial_patches.json').read_text(encoding='utf-8'))
        for old, new in trials:
            if old in source:
                source = source.replace(old, new, 1)
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
    source = ui(source, name)
    if had_recovery:
        from install_recovery_factory import patch_ui as recovery_ui
        source = recovery_ui(source, name, recovery_assets)
    if had_preanalysis:
        from install_preanalysis import patch_screen
        source = patch_screen(source)
    if name == "job_status.py":
        source = status_layout(source)
        source = restart_mesh(source)
    if dock_edits:
        source = variant_ui(source, dock_edits, 'toolhead')
    if had_paused_tools:
        source = add_subscription(source)
    compile(source, name, 'exec')
    return source


def restart_mesh(source):
    path = Path(__file__).with_name('print_features') / 'restart_mesh_patches.json'
    source = source.replace('        if self.state == "cancelled":\n            self.restart_cancelled()\n            return\n',
                            '        if self.state == "cancelled" and "SCREEN_MESH_SELECT" in self._printer.available_commands:\n            self.restart_cancelled()\n            return\n')
    for before, after in json.loads(path.read_text(encoding='utf-8')):
        source = once(source, before, after)
    return source


def install(home, screen, klipper, backup):
    assets = Path(__file__).with_name('print_features')
    config = home / 'printer_data/config'
    changes = {}
    for name, relative in [('job_status.py', 'panels/job_status.py'), ('gcodes.py', 'panels/gcodes.py'),
                           ('screen_panel.py', 'ks_includes/screen_panel.py'), ('screen.py', 'screen.py')]:
        path = screen / relative
        changes[path] = patch_ui(path.read_text(encoding='utf-8'), name)
    panel = screen / "panels/main_menu.py"
    changes[panel] = home_panel(panel.read_text(encoding="utf-8"))
    handler = screen / 'ks_includes/notification_handler.py'
    changes[handler] = notification(handler.read_text(encoding='utf-8'))
    changes[klipper / 'klippy/extras/probe_auto_recovery.py'] = (assets / 'probe_auto_recovery.py').read_text(encoding='utf-8')
    changes[klipper / 'klippy/extras/exclude_tool_guard.py'] = (assets / 'exclude_tool_guard.py').read_text(encoding='utf-8')
    changes[screen / 'panels/exclude.py'] = (assets / 'exclude.py').read_text(encoding='utf-8')
    changes[screen / 'ks_includes/widgets/objectmap.py'] = (assets / 'objectmap.py').read_text(encoding='utf-8')
    for name in ('print_controls.py', 'toolchange_count.py', 'restart_notice.py', 'info_marquee.py', 'exclusion_eta.py'):
        changes[screen / 'ks_includes' / name] = (assets / name).read_text(encoding='utf-8')
    changes[klipper / 'klippy/extras/print_sensor.py'] = (assets / 'print_sensor.py').read_text(encoding='utf-8')
    changes[klipper / 'klippy/extras/screen_mesh.py'] = (assets / 'screen_mesh.py').read_text(encoding='utf-8')
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
    if not re.search(r'^\[exclude_tool_guard\]\s*$', text, re.M):
        text = text.replace('[print_sensor]', '[print_sensor]\n[exclude_tool_guard]', 1)
    from mesh_features import header
    changes[p] = header(text, config)
    if os.environ.get('LUGOWARE_SYSTEM_ONLY') != '1':
        p = config / 'printer_base.cfg'
        changes[p] = feature_macros(p.read_text(encoding='utf-8'))
    from mesh_features import config as mesh_config
    p = config / 'printer_base.cfg'
    changes[p] = mesh_config(changes.get(p, p.read_text(encoding='utf-8')))
    from followup_features import first_tool
    changes[p] = first_tool(changes[p])
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
