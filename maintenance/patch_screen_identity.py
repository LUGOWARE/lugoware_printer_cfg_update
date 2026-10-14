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



VERSION_METHOD = r'''    def update_time(self):
        # LUGOWARE config version in the former clock position.
        import pathlib
        import re
        path = pathlib.Path.home() / "printer_data/config/printer_base.cfg"
        try:
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            if stamp != getattr(self, "_config_version_stamp", None):
                with path.open(encoding="utf-8-sig") as source:
                    header = source.read(8192)
                match = re.search(r"(?mi)^\s*#\s*FLEX4_[^\r\n]*?_(V\d+(?:\.\d+)+)(?=[-\s]|$)", header)
                version = match.group(1).upper() if match else "V—"
                self._config_version_stamp = stamp
                self.control["time"].set_text(version)
        except (OSError, UnicodeError):
            self._config_version_stamp = None
            if self.control["time"].get_text() != "V—":
                self.control["time"].set_text("V—")
        return True
'''


def patch_version(source):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ('Panel', 'BasePanel'))
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'update_time')
    lines = source.splitlines(keepends=True)
    lines[method.lineno-1:method.end_lineno] = [VERSION_METHOD]
    source = ''.join(lines)
    if '# LUGOWARE version label style' not in source:
        tree = ast.parse(source)
        labels = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                  and any(ast.unparse(t) == "self.control['time']" for t in n.targets)]
        if len(labels) != 1:
            raise ValueError('Unsupported base_panel.py clock label')
        node = labels[0]
        lines = source.splitlines(keepends=True)
        lines[node.lineno-1:node.end_lineno] = [
            '        # LUGOWARE version label style\n'
            '        from gi.repository import Pango\n'
            '        self.control["time"] = Gtk.Label(label="V—")\n'
            '        version_style = Pango.AttrList()\n'
            '        version_style.insert(Pango.attr_scale_new(0.8))\n'
            '        self.control["time"].set_attributes(version_style)\n']
        source = ''.join(lines)
    compile(source, 'base_panel.py', 'exec')
    return source


def main():
    panels = Path(os.environ.get('KLIPPERSCREEN_DIR', Path.home() / 'KlipperScreen')) / 'panels'
    replacements = {}
    for name, transform in [('base_panel.py', lambda text: patch_version(patch_base(text)))]:
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
    print('[확인 완료] 메인 화면 현재 IP / 상단 설정 버전 표시')


if __name__ == '__main__':
    main()
