"""Detached, serialized Mainsail jobs. Git download completion is not install completion."""
import configparser
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from check_idle import main as check_idle, request
from install_screen_config import merge
from patch_print_controls import macros, feature_macros
from preserve_sensor_pins import preserve
from install_toolhead_variant import plan as variant_plan, selected as selected_variant, commit as commit_variant
from install_toolhead_variant import restore as restore_variant


def atomic(path, data):
    temporary = path.with_name(path.name + '.pending')
    temporary.write_bytes(data)
    os.replace(temporary, path)


def validate_config(text, screen, home):
    cfg = configparser.RawConfigParser(strict=True)
    cfg.read_string(text)
    macros(text)
    if '#*# <' in text:
        raise ValueError('SAVE_CONFIG belongs in printer.cfg, not printer_base.cfg')
    registered = set()
    for name in ('fast_cancel.py', 'lugo_tool_temperature.py'):
        code = (home / 'klipper/klippy/extras' / name).read_text(encoding='utf-8')
        registered.update(re.findall(r"register_command\(['\"]([A-Z_]+)['\"]", code))
    required = set(re.findall(r'^\s*((?:FAST_CANCEL|LUGO_SET_TOOL_TEMP)[A-Z_]*)\b', text, re.M))
    if required - registered:
        raise ValueError('Update lugoware_system first; missing commands: ' + ', '.join(sorted(required - registered)))
    for panel in re.findall(r'^\s*panel\s*[:=]\s*([a-z_]+)\s*$', screen, re.M):
        if not (home / 'KlipperScreen/panels' / (panel + '.py')).is_file():
            raise ValueError('Update lugoware_system first; missing panel: ' + panel)


def apply_config(repo, home, backup):
    target = home / 'printer_data/config'
    variant = selected_variant(home)
    source = repo / 'printer_base.cfg'
    auxiliary = repo / 'printer_base_toolhead.cfg'
    if variant == 'toolhead' and auxiliary.is_file():
        source = auxiliary
    base = source.read_text(encoding='utf-8-sig')
    base = preserve(base, target / 'printer.cfg')
    if (home / 'klipper/klippy/extras/print_sensor.py').is_file():
        base = feature_macros(base)
        guard = home / 'klipper/klippy/extras/exclude_tool_guard.py'
        if guard.is_file() and 'def prepare_first(' in guard.read_text(encoding='utf-8'):
            from followup_features import first_tool
            base = first_tool(base)
    screen_source = repo / 'KlipperScreen.conf'
    auxiliary_screen = repo / 'KlipperScreen_toolhead.conf'
    auxiliary_path = repo / 'toolhead_auxiliary.cfg'
    auxiliary_config = None
    if variant == 'toolhead':
        if auxiliary_screen.is_file():
            screen_source = auxiliary_screen
        if auxiliary_path.is_file():
            auxiliary_config = auxiliary_path.read_text(encoding='utf-8-sig')
    template = screen_source.read_text(encoding='utf-8-sig')
    previous_screen = (target / 'KlipperScreen.conf').read_text(encoding='utf-8')
    if (home / 'klipper/klippy/extras/print_sensor.py').is_file() and '[menu __print lock]' not in template:
        template += '\n[menu __print lock]\nenable: False\n'
    screen = merge(previous_screen, template)
    if (home / 'klipper/klippy/extras/lugo_diagnostics.py').is_file():
        from install_diagnostics import strip_legacy, screen_menu
        from home_lighting import printer_config, screen_config
        base = printer_config(strip_legacy(base))
        screen = screen_menu(screen_config(screen))
    validate_config(base, screen, home)
    changes = {'printer_base.cfg': base.encode(), 'KlipperScreen.conf': screen.encode()}
    header_name = 'printer_header_toolhead.cfg' if variant == 'toolhead' else 'printer_header.cfg'
    header_path = repo / header_name
    header_template = header_path.read_text(encoding='utf-8-sig') if header_path.is_file() else None
    variant_changes = variant_plan(home, variant, Path(__file__).with_name('toolhead_variant'),
                                   base_override=base, screen_override=screen, auxiliary_override=auxiliary_config,
                                   header_template=header_template)
    previous = {name: (target / name).read_bytes() for name in changes}
    for name, content in previous.items():
        (backup / name).write_bytes(content)
    check_idle()
    combined = {target / name: content for name, content in changes.items()}
    combined.update(variant_changes)
    variant_backup = backup / 'hardware-variant'
    commit_variant(combined, variant_backup)
    try:
        activate_config()
    except (Exception, SystemExit) as exc:
        print('Config activation failed; restoring previous files from ' + str(variant_backup), flush=True)
        try:
            restore_variant(variant_backup)
            activate_config()
        except (Exception, SystemExit) as rollback_error:
            raise RuntimeError('Config activation failed (%s); automatic recovery did not finish (%s). Backup: %s'
                               % (exc, rollback_error, variant_backup)) from rollback_error
        raise RuntimeError('Config activation failed (%s); previous files restored and services ready. Backup: %s'
                           % (exc, variant_backup)) from exc


def activate_config():
    subprocess.run(['sudo', '-n', 'systemctl', 'restart', 'klipper', 'KlipperScreen'], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name('wait_ready.py')), '--ready-only'], check=True)
    subprocess.run(['systemctl', 'is-active', '--quiet', 'KlipperScreen'], check=True)


def sync_latest_config(home, branch, backup):
    """Fetch the model configuration before reporting system installation success."""
    if branch not in ('FLEX4_M', 'FLEX4_L', 'FLEX4_W'):
        raise ValueError('Unrecognized model branch')
    repo = home / 'lugoware_config'
    git = ['git', '-c', 'core.hooksPath=/dev/null', '-C', str(repo)]
    def output(*args):
        return subprocess.check_output(git + list(args), text=True).strip()
    if output('branch', '--show-current') != branch:
        raise RuntimeError('Config model branch changed; preserved without modification')
    if output('status', '--porcelain'):
        raise RuntimeError('Local config repository edits preserved; resolve before updating system')
    url = 'https://github.com/LUGOWARE/lugoware_printer_cfg_update.git'
    if output('remote', 'get-url', 'origin') not in (url, url[:-4]):
        raise RuntimeError('Unexpected config origin; preserved without modification')
    # Explicit official source and ref; do not trust a custom origin fetch refspec.
    subprocess.run(git + ['fetch', url, 'refs/heads/' + branch], check=True)
    commit = output('rev-parse', 'FETCH_HEAD')
    subprocess.run(git + ['merge-base', '--is-ancestor', 'HEAD', commit], check=True)
    subprocess.run(git + ['merge', '--ff-only', commit], check=True)
    backup.mkdir(parents=True, exist_ok=True)
    snapshot = backup / 'source'
    snapshot.mkdir()
    for name in ('printer_base.cfg', 'KlipperScreen.conf'):
        data = subprocess.check_output(git + ['show', commit + ':' + name])
        (snapshot / name).write_bytes(data)
    if selected_variant(home) == 'toolhead':
        names = ('printer_base_toolhead.cfg', 'KlipperScreen_toolhead.conf', 'toolhead_auxiliary.cfg')
        available = set(output('ls-tree', '--name-only', commit, '--', *names).splitlines())
        for name in names:
            if name in available:
                (snapshot / name).write_bytes(subprocess.check_output(git + ['show', commit + ':' + name]))
    header_name = 'printer_header_toolhead.cfg' if selected_variant(home) == 'toolhead' else 'printer_header.cfg'
    if (repo / header_name).is_file():
        (snapshot / header_name).write_bytes(subprocess.check_output(git + ['show', commit + ':' + header_name]))
    print('Applying latest model config: ' + branch + ' ' + commit, flush=True)
    apply_config(snapshot, home, backup)
    print('System and model config applied: ' + commit, flush=True)


def wait_manager():
    # Never call a nested Moonraker update while its Git/full-update lock is held.
    for _ in range(1800):
        try:
            if request('/machine/update/status').get('busy') is False:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError('Moonraker remained busy; restart this update service to retry')


def wait_system(state_dir):
    path = state_dir / 'system-status.json'
    for _ in range(3600):
        if not path.exists():
            return
        state = json.loads(path.read_text())['state']
        if state == 'complete':
            return
        if state not in ('queued', 'running'):
            raise RuntimeError('Finish/retry lugoware_system before applying config')
        time.sleep(2)
    raise RuntimeError('System installation did not finish; inspect its log before retrying config')


def run(channel):
    if channel not in ('config', 'system'):
        raise ValueError('Unknown channel')
    home = Path.home()
    state_dir = home / '.local/share/lugoware'
    state_dir.mkdir(parents=True, exist_ok=True)
    status_file = state_dir / (channel + '-status.json')
    try:
        previous = json.loads(status_file.read_text())
    except (OSError, ValueError):
        previous = None
    run_id = str(time.time_ns())
    log = home / 'printer_data/logs' / ('lugoware_' + channel + '.log')
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a', buffering=1) as output:
        os.dup2(output.fileno(), 1)
        os.dup2(output.fileno(), 2)
        def status(state, detail):
            atomic(status_file, json.dumps(dict(channel=channel, state=state, detail=detail,
                run_id=run_id, time=time.time(), log=str(log))).encode())
            print(state + ': ' + detail, flush=True)
        status('queued', 'Waiting for other updates. Download complete does not mean installation complete.')
        try:
            wait_manager()
            if channel == 'config':
                # Full Update may have queued both services. Give system priority
                # without holding the shared lock it needs to finish.
                wait_system(state_dir)
            with (state_dir / 'update.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                check_idle(previous=previous)
                if channel == 'config':
                    system_status = state_dir / 'system-status.json'
                    if system_status.exists() and json.loads(system_status.read_text())['state'] != 'complete':
                        raise RuntimeError('Finish/retry lugoware_system before applying config')
                subprocess.run(['sudo', '-n', 'true'], check=True)
                repo = home / ('lugoware_' + channel)
                commit = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
                if subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain']).strip():
                    raise RuntimeError('Local repository edits preserved; resolve before updating')
                backup = home / 'lugoware_backups' / (channel + '-' + run_id)
                backup.mkdir(parents=True)
                snapshot = backup / 'source'
                if channel == 'system':
                    snapshot = Path(subprocess.check_output(
                        ['sudo', '--lugoware-prepare', commit], text=True).strip())
                    if snapshot != Path('/var/lib/lugoware-updates') / commit:
                        raise RuntimeError('Unexpected trusted release path')
                else:
                    shutil.copytree(repo, snapshot, ignore=shutil.ignore_patterns('.git', '__pycache__'))
                status('running', commit + '; backup: ' + str(backup))
                if channel == 'config':
                    apply_config(snapshot, home, backup)
                else:
                    branch = subprocess.check_output(['git', '-C', str(home / 'lugoware_config'),
                        'branch', '--show-current'], text=True).strip()
                    if branch not in ('FLEX4_M', 'FLEX4_L', 'FLEX4_W'):
                        raise ValueError('Unrecognized model branch')
                    # Runs outside Moonraker's cgroup; its restarts cannot kill this job.
                    subprocess.run(['bash', str(snapshot / 'install.sh'), '--system-update', branch],
                                   stdin=subprocess.DEVNULL, check=True)
                status('complete', commit)
        except (Exception, SystemExit) as exc:
            status('failed', str(exc) + '; resolve the cause, then retry Update in Mainsail (or restart the update service)')
            raise


if __name__ == '__main__':
    if sys.argv[1] == '--sync-config':
        sync_latest_config(Path.home(), sys.argv[2], Path(sys.argv[3]))
    else:
        run(sys.argv[1])
