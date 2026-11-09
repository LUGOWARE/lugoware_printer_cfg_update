"""Install shared multilingual panels, retaining the previous files."""
import argparse
from pathlib import Path
import shutil

FILES = ('extrude.py', 'nozzle_temperature.py', 'tool_prepare.py', 'tool_temperature.py', 'fan.py', 'fine_tune.py', 'settings.py', 'network.py', 'console.py', 'system.py', 'move.py', 'move_advanced.py')
RUNTIME = ('ks_includes/sdbus_nm.py', 'ks_includes/widgets/scroll.py')


def install(source, target, backup, check=False):
    if not target.is_dir():
        raise FileNotFoundError(f'KlipperScreen panels directory missing: {target}')
    # Validate the complete set before replacing any existing panel.
    for name in FILES:
        compile((source / name).read_bytes(), name, 'exec')
        if (target / name).exists() and not (target / name).is_file():
            raise ValueError(f'Not a file: {target / name}')
    runtime_source = source.parent / 'runtime'
    pairs = [(source / name, target / name, backup / name) for name in FILES]
    pairs += [(runtime_source / name, target.parent / name, backup / 'runtime' / name)
              for name in RUNTIME]
    # Validate runtime and panels together before touching the installed screen.
    for src, dest, saved in pairs:
        compile(src.read_bytes(), str(src), 'exec')
        if dest.exists() and not dest.is_file():
            raise ValueError(f'Not a file: {dest}')
    if check:
        return
    for src, dest, saved in pairs:
        if dest.exists() and dest.read_bytes() == src.read_bytes():
            continue
        if dest.exists() and not saved.exists():
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, saved)
    for src, dest, saved in pairs:
        if dest.exists() and dest.read_bytes() == src.read_bytes():
            print(f'  [SKIP] {dest.name}: already installed', flush=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        if dest.read_bytes() != src.read_bytes():
            raise IOError(f'Panel verification failed: {dest}')
        print(f'  [OK] {dest.name}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', help='Legacy option; panels now use the screen language')
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / 'panels' / 'common'
    install(source, args.target, args.backup, args.check)
