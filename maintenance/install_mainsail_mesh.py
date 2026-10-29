"""Install the mesh switch in the local Mainsail confirmation dialog."""
import os
from pathlib import Path
import re
import shutil


def patch(source):
    source = re.sub(r'<script\b[^>]*src=["\'][^"\']*lugoware-mesh\.js[^"\']*["\'][^>]*></script>', '', source)
    if source.count('</body>') != 1:
        raise ValueError('Unsupported Mainsail HTML document')
    return source.replace('</body>', '<script src="./lugoware-mesh.js?v=20261029"></script></body>')


if __name__ == '__main__':
    folder = Path(os.environ.get('MAINSAIL_DIR', Path.home() / 'mainsail'))
    index = folder / 'index.html'
    if not index.is_file():
        print('Mainsail is not installed locally; mesh switch skipped.')
    else:
        result = patch(index.read_text(encoding='utf-8'))
        backup = Path(os.environ['BACKUP_DIR']) / 'mainsail-mesh'
        backup.mkdir(parents=True, exist_ok=True)
        if not (backup / 'index.html').exists():
            shutil.copy2(index, backup / 'index.html')
        target = folder / 'lugoware-mesh.js'
        if target.exists() and not (backup / target.name).exists():
            shutil.copy2(target, backup / target.name)
        shutil.copy2(Path(__file__).with_name('mainsail_mesh.js'), target)
        index.write_text(result, encoding='utf-8')
        print('Mainsail bed mesh switch installed; refresh browser once.')
