"""Give X11 KlipperScreen a D-Bus session independent of SSH logins."""
import os
from pathlib import Path
import shutil


def patch(source):
    old = '    exec /usr/bin/xinit $KS_XCLIENT'
    new = '    exec /usr/bin/dbus-run-session -- /usr/bin/xinit $KS_XCLIENT'
    if new in source:
        return source
    if source.count(old) != 1:
        raise ValueError('Unsupported KlipperScreen X11 launcher')
    return source.replace(old, new)


if __name__ == '__main__':
    if not Path('/usr/bin/dbus-run-session').is_file():
        raise RuntimeError('dbus-run-session is required for an independent screen session')
    screen = Path(os.environ.get('KLIPPERSCREEN_DIR', Path.home() / 'KlipperScreen'))
    target = screen / 'scripts/KlipperScreen-start.sh'
    source = target.read_text(encoding='utf-8')
    result = patch(source)
    if result != source:
        backup = Path(os.environ['BACKUP_DIR']) / 'screen-session/KlipperScreen-start.sh'
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy2(target, backup)
        target.write_text(result, encoding='utf-8')
    print('KlipperScreen X11 uses a private D-Bus session; SSH logout cannot close its bus.')
