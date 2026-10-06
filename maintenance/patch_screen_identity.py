"""Patch the main-screen title to display the current local network address."""
import ast
import os
from datetime import datetime
from pathlib import Path
import shutil


HELPER = '''
def _lugoware_network_address():
    import ipaddress
    import json
    import subprocess
    try:
        # Route lookup sends no network packets, and selects the active interface.
        routes = json.loads(subprocess.check_output(
            ['ip', '-j', 'route', 'get', '1.1.1.1'], timeout=1, text=True))
        address = routes[0].get('prefsrc') or routes[0].get('src')
        if address and not ipaddress.ip_address(address).is_loopback:
            return address
    except Exception:
        pass
    try:
        addresses = subprocess.check_output(['hostname', '-I'], timeout=1, text=True).split()
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.version == 4 and not ip.is_loopback and not ip.is_link_local:
                return address
    except Exception:
        pass
    return 'IP —'

'''


def patch_base(source):
    if '# LUGOWARE main IP title' in source:
        return source
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ('Panel', 'BasePanel'))
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'set_title')
    lines = source.splitlines(keepends=True)
    branches = [n for n in method.body if isinstance(n, ast.If) and ast.unparse(n.test) == 'not title']
    if len(branches) != 1:
        raise ValueError('Unsupported base_panel.py title structure')
    branch = branches[0]
    lines[branch.lineno:branch.end_lineno] = [
        '            # LUGOWARE main IP title\n',
        '            self.titlelbl.set_label(_lugoware_network_address())\n',
        '            return\n',
    ]
    # Append helper after the class, so imports/future imports stay in place.
    return ''.join(lines) + '\n' + HELPER


def main():
    panels = Path(os.environ.get('KLIPPERSCREEN_DIR', Path.home() / 'KlipperScreen')) / 'panels'
    replacements = {}
    for name, transform in [('base_panel.py', patch_base)]:
        path = panels / name
        old = path.read_text(encoding='utf-8')
        new = transform(old)
        compile(new, str(path), 'exec')
        if old != new:
            replacements[path] = new
    backup = Path(os.environ.get('BACKUP_DIR', Path.home() / 'lugoware_backups' / ('screen-ip-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f')))) / 'screen-identity'
    if replacements:
        backup.mkdir(parents=True)
        for path in replacements:
            if not (backup / path.name).exists():
                shutil.copy2(path, backup / path.name)
        try:
            for path, content in replacements.items():
                path.write_text(content, encoding='utf-8')
        except Exception:
            for path in replacements:
                shutil.copy2(backup / path.name, path)
            raise
        print('Backup:', backup)
    print('[확인 완료] 메인 화면 현재 IP 표시')


if __name__ == '__main__':
    main()
