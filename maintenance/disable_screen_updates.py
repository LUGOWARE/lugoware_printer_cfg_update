"""Comment out only the KlipperScreen update manager section."""
import argparse
from pathlib import Path
import re
import shutil
import glob
import hashlib


def comment_section(text, names=('KlipperScreen',)):
    targets = {'update_manager ' + name.casefold() for name in names}
    result = []
    active = False
    for line in text.splitlines(keepends=True):
        section = re.match(r'^\s*\[([^\]]+)\]', line)
        if section:
            active = section.group(1).strip().casefold() in targets
        if active and line.strip() and not line.lstrip().startswith(('#', ';')):
            line = '#' + line
        result.append(line)
    return ''.join(result)


def apply(path, backup, names=('KlipperScreen',)):
    original = path.read_bytes()
    updated = comment_section(original.decode('utf-8'), names).encode('utf-8')
    if updated == original:
        return False
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_bytes(updated)
    return True


def apply_tree(path, backup, names):
    # Resolve active Moonraker includes as well as the main configuration.
    pending, seen, files = [path], set(), []
    while pending:
        current = pending.pop().resolve()
        if current in seen:
            continue
        seen.add(current)
        text = current.read_text(encoding='utf-8')
        files.append(current)
        for pattern in re.findall(r'^\s*\[include\s+([^\]]+)\]', text, re.MULTILINE):
            pattern = Path(pattern.strip()).expanduser()
            if not pattern.is_absolute():
                pattern = current.parent / pattern
            pending.extend(Path(name) for name in sorted(glob.glob(str(pattern))) if Path(name).is_file())
    changed = False
    for current in files:
        key = hashlib.sha256(str(current).encode()).hexdigest()[:16]
        saved = backup / (key + '-' + current.name)
        if apply(current, saved, names):
            changed = True
    return changed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('backup', type=Path)
    parser.add_argument('--installed-components', action='store_true')
    args = parser.parse_args()
    if args.installed_components:
        changed = apply_tree(args.config, args.backup, ('klipper', 'KlipperScreen', 'mainsail-config', 'moonraker'))
    else:
        changed = apply(args.config, args.backup)
    print('changed' if changed else 'unchanged')
