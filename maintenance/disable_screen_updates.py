"""Comment out only the KlipperScreen update manager section."""
import argparse
from pathlib import Path
import re
import shutil


def comment_section(text):
    result = []
    active = False
    for line in text.splitlines(keepends=True):
        section = re.match(r'^\s*\[([^\]]+)\]', line)
        if section:
            active = section.group(1).strip().casefold() == 'update_manager klipperscreen'
        if active and line.strip() and not line.lstrip().startswith(('#', ';')):
            line = '#' + line
        result.append(line)
    return ''.join(result)


def apply(path, backup):
    original = path.read_bytes()
    updated = comment_section(original.decode('utf-8')).encode('utf-8')
    if updated == original:
        return False
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_bytes(updated)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('backup', type=Path)
    args = parser.parse_args()
    print('changed' if apply(args.config, args.backup) else 'unchanged')
