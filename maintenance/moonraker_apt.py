"""Scope official Moonraker APT calls without changing system repository files."""
from contextlib import contextmanager
from pathlib import Path
import os
import re
import shlex
import tempfile


def scoped_script(text, folder, sources):
    options = ['-o', 'Dir::Etc::sourcelist=' + str(sources),
               '-o', 'Dir::Etc::sourceparts=-',
               '-o', 'Acquire::http::No-Cache=true',
               '-o', 'Acquire::https::No-Cache=true',
               '-o', 'Acquire::Retries=2', '-o', 'Acquire::http::Timeout=30',
               '-o', 'Acquire::https::Timeout=30', '-o', 'DPkg::Lock::Timeout=120',
               '-o', 'APT::Update::Error-Mode=any']
    # The temporary script is outside scripts/, so retain the real source root.
    text, count = re.subn(r'^SRCDIR=.*$', lambda m: 'SRCDIR=' + shlex.quote(str(folder)), text, flags=re.M)
    if count != 1:
        raise ValueError('Unsupported Moonraker installer source directory')
    if not all(re.search(r'^\s*sudo apt-get ' + command + r'\b', text, re.M)
               for command in ('update', 'install')):
        raise ValueError('Unsupported Moonraker installer APT commands')
    text = re.sub(r'(?m)^([ \t]*)sudo apt-get(?=\s)',
                  lambda m: m[1] + 'sudo apt-get ' + shlex.join(options), text)
    return text


@contextmanager
def installer(folder):
    original = folder/'scripts/install-moonraker.sh'
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('VERSION_CODENAME', '').strip('"') != 'bullseye':
        yield original
        return
    with tempfile.TemporaryDirectory(prefix='lugoware-moonraker-apt-') as tmp:
        work = Path(tmp)
        os.chmod(work, 0o755)
        sources = work/'sources.list'
        sources.write_text('deb https://deb.debian.org/debian bullseye main\n'
                           'deb https://deb.debian.org/debian bullseye-updates main\n'
                           'deb https://archive.debian.org/debian-security bullseye-security main\n')
        os.chmod(sources, 0o644)
        script = work/'install-moonraker.sh'
        script.write_text(scoped_script(original.read_text(), folder.resolve(), sources))
        print('[확인] Moonraker 의존성은 Debian 공식 저장소만 사용 (시스템 Armbian 설정 유지)', flush=True)
        yield script
