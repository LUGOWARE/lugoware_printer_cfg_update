"""Comment obsolete bullseye-backports entries without changing other sources."""
import argparse
from pathlib import Path
import re
import shutil


def repair(root, backup):
    paths = [root / 'sources.list', *sorted((root / 'sources.list.d').glob('*.list'))]
    changed = 0
    pattern = re.compile(r'^[ \t]*deb(?:-src)?[ \t]+[^\r\n]*[ \t]bullseye-backports(?:[ \t]|$)', re.MULTILINE)
    for path in paths:
        if not path.is_file():
            continue
        original = path.read_bytes()
        text = original.decode('utf-8')
        updated = pattern.sub(lambda m: '#' + m.group(0), text).encode('utf-8')
        if updated == original:
            continue
        saved = backup / path.relative_to(root)
        saved.parent.mkdir(parents=True, exist_ok=True)
        if not saved.exists():
            shutil.copy2(path, saved)
        path.write_bytes(updated)
        changed += 1
    print(f'[확인] bullseye-backports 저장소 주석 처리: {changed}개 파일 (기존 파일 백업)', flush=True)
    return changed


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('backup', type=Path)
    args = parser.parse_args()
    repair(Path('/etc/apt'), args.backup)
