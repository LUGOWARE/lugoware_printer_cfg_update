"""Preserve Moonraker's existing service allowlist and permit sonar restart."""
import os
from pathlib import Path
import shutil


def allow_sonar(path, backup):
    # Moonraker creates this with its standard services. Do not replace a missing
    # list with a sonar-only list, which could remove other service permissions.
    original = path.read_bytes()
    text = original.decode('utf-8')
    if any(line.strip() == 'sonar' for line in text.splitlines()):
        return False
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(path, backup)
    newline = b'\r\n' if b'\r\n' in original else b'\n'
    updated = original
    if updated and not updated.endswith(b'\n'):
        updated += newline
    updated += b'sonar' + newline
    path.write_bytes(updated)
    return True


if __name__ == '__main__':
    path = Path.home() / 'printer_data/moonraker.asvc'
    backup = Path(os.environ['BACKUP_DIR']) / 'moonraker.asvc'
    changed = allow_sonar(path, backup)
    print('[완료] sonar 서비스 재시작 권한 추가' if changed else
          '[건너뜀] sonar 서비스 재시작 권한: 이미 등록됨', flush=True)
