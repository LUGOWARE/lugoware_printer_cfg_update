"""Install the selected language panels, retaining the previous files."""
import argparse
from pathlib import Path
import shutil

FILES = ('extrude.py', 'nozzle_temperature.py', 'tool_prepare.py')


def install(source, target, backup, check=False):
    if not target.is_dir():
        raise FileNotFoundError(f'KlipperScreen panels directory missing: {target}')
    # Validate the complete set before replacing any existing panel.
    for name in FILES:
        compile((source / name).read_bytes(), name, 'exec')
        if (target / name).exists() and not (target / name).is_file():
            raise ValueError(f'Not a file: {target / name}')
    if check:
        return
    backup.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        dest = target / name
        if dest.exists() and not (backup / name).exists():
            shutil.copy2(dest, backup / name)
    for name in FILES:
        dest = target / name
        shutil.copyfile(source / name, dest)
        if dest.read_bytes() != (source / name).read_bytes():
            raise IOError(f'Panel verification failed: {name}')
        print(f'  [OK] {name}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=('ko', 'en'), required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / 'panels' / args.language
    install(source, args.target, args.backup, args.check)
