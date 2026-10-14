"""Install an idempotent Mainsail reconnect helper without rebuilding its assets."""
import os
import re
from pathlib import Path
import shutil

TAG = '<script defer src="./lugoware-reconnect.js?v=3"></script>'


def patch(source):
    source = re.sub(r'<script\s+defer\s+src="\./lugoware-reconnect\.js\?v=\d+"></script>', TAG, source)
    if TAG in source:
        return source
    if source.count('</head>') != 1:
        raise ValueError('Unsupported Mainsail HTML document')
    return source.replace('</head>', TAG + '\n</head>')


if __name__ == '__main__':
    folder = Path(os.environ.get('MAINSAIL_DIR', Path.home() / 'mainsail'))
    index = folder / 'index.html'
    if not index.is_file():
        print('Mainsail is not installed locally; reconnect helper skipped.')
    else:
        source = index.read_text(encoding='utf-8')
        result = patch(source)
        backup = Path(os.environ['BACKUP_DIR']) / 'mainsail-reconnect'
        backup.mkdir(parents=True, exist_ok=True)
        if not (backup / 'index.html').exists():
            shutil.copy2(index, backup / 'index.html')
        shutil.copy2(Path(__file__).with_name('mainsail_reconnect.js'), folder / 'lugoware-reconnect.js')
        index.write_text(result, encoding='utf-8')
        print('Mainsail reconnect helper installed; refresh browser once to load it.')
