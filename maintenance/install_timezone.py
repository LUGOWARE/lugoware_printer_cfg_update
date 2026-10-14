"""Install timezone UI without changing the selected system timezone."""
import argparse
import os
from pathlib import Path
import pwd
import re
import shutil


def patch_settings(source):
    anchor = '        self.content.add(self.labels["settings_menu"])'
    block = '''        # LUGOWARE timezone settings (system setting survives config updates).
        from panels.timezone import setting_title
        zone_title = setting_title(self._config.get_main_config())
        self.add_option('settings', self.settings, 'timezone', {
            'name': zone_title, 'type': 'button',
            'callback': lambda widget, name: self._screen.show_panel('timezone', title=zone_title),
        })
'''
    if '# LUGOWARE timezone settings' in source:
        source = re.sub(r'(?ms)^        # LUGOWARE timezone settings.*?(?=^        self.content.add\(self.labels\["settings_menu"\]\))', '', source)
    if source.count(anchor) != 1:
        raise ValueError('Unsupported settings panel structure')
    result = source.replace(anchor, block + anchor)
    compile(result, 'settings.py', 'exec')
    return result


def install_ui(screen, backup):
    root = Path(__file__).resolve().parents[1]
    settings = screen / 'panels/settings.py'
    changes = {settings: patch_settings(settings.read_text(encoding='utf-8')).encode(),
               screen / 'panels/timezone.py': (root / 'panels/common/timezone.py').read_bytes()}
    for path in Path(__file__).with_name('timezone_locales').iterdir():
        changes[screen / 'panels/timezone_locales' / path.name] = path.read_bytes()
    for target, data in changes.items():
        if target.suffix == '.py': compile(data, str(target), 'exec')
    for target, data in changes.items():
        if target.exists() and target.read_bytes() == data: continue
        saved = backup / target.relative_to(screen)
        if target.exists() and not saved.exists():
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    print('Timezone country/city UI installed; current timezone preserved.')


def policy(user, legacy):
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', user): raise ValueError('Invalid user')
    if legacy:
        return ('[Allow printer user to select timezone]\nIdentity=unix-user:' + user + '\n'
                'Action=org.freedesktop.timedate1.set-timezone\n'
                'ResultAny=yes\nResultInactive=yes\nResultActive=yes\n')
    return ('polkit.addRule(function(action, subject) {\n'
            '    if (action.id === "org.freedesktop.timedate1.set-timezone" && '
            'subject.user === "' + user + '") { return polkit.Result.YES; }\n});\n')


def install_permission(user):
    if os.geteuid() != 0: raise PermissionError('Initial SSH installation requires sudo')
    policy(user, True)  # Validate before using the name.
    if pwd.getpwnam(user).pw_dir != '/home/' + user: raise ValueError('Unexpected user home')
    legacy = Path('/etc/polkit-1/localauthority').is_dir()
    path = Path('/etc/polkit-1/localauthority/50-local.d/60-lugoware-timezone.pkla' if legacy
                else '/etc/polkit-1/rules.d/60-lugoware-timezone.rules')
    path.parent.mkdir(parents=True, exist_ok=True)
    for parent in (path.parent, *path.parent.parents):
        if parent.is_symlink() or parent.stat().st_uid != 0 or parent.stat().st_mode & 0o022:
            raise PermissionError('Untrusted policy directory')
    if path.is_symlink(): raise PermissionError('Unexpected policy symlink')
    path.write_text(policy(user, legacy), encoding='utf-8')
    os.chown(path, 0, 0)
    path.chmod(0o644)
    print('Registered timezone-only permission. Current timezone unchanged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--permissions', metavar='USER')
    args = parser.parse_args()
    if args.permissions:
        install_permission(args.permissions)
    else:
        install_ui(Path(os.environ.get('KLIPPERSCREEN_DIR', Path.home() / 'KlipperScreen')),
                   Path(os.environ['BACKUP_DIR']) / 'timezone')
