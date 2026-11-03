"""Configure one existing NTP provider, or install timesyncd. Run while idle."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

SERVERS = ('ntp.aliyun.com', 'time.cloudflare.com', 'time.google.com')
UNITS = ('chrony.service', 'chronyd.service', 'ntp.service', 'ntpsec.service', 'systemd-timesyncd.service')


def run(*args):
    result = subprocess.run(list(args), text=True, capture_output=True)
    if result.returncode:
        print(result.stdout + result.stderr, flush=True)
        result.check_returncode()
    return result


def select_provider(states):
    active = [unit for unit, (loaded, running) in states.items() if loaded and running]
    if len(active) > 1:
        raise RuntimeError('Multiple time services active; inspect before changing: ' + ', '.join(active))
    if active:
        return active[0]
    return next((unit for unit in UNITS if states.get(unit, (False, False))[0]), None)


def config_text(kind, old):
    if kind == 'systemd-timesyncd.service':
        return '[Time]\nNTP=' + ' '.join(SERVERS) + '\nFallbackNTP=pool.ntp.org\n'
    begin, end = '# LUGOWARE TIME SYNC BEGIN', '# LUGOWARE TIME SYNC END'
    if begin in old:
        start = old.index(begin)
        finish = old.index(end, start) + len(end)
        old = old[:start] + old[finish:]
    added = ['server ' + host + ' iburst' for host in SERVERS
             if not any(line.split('#', 1)[0].split()[1:2] == [host] for line in old.splitlines())]
    if kind.startswith('chrony'):
        directives = {line.split()[0] for line in old.splitlines() if line.strip() and not line.lstrip().startswith('#')}
        if 'makestep' not in directives:
            added.append('makestep 1.0 3')
        if not {'rtcfile', 'rtcsync'} & directives:
            added.append('rtcsync')
    return old.rstrip() + '\n\n' + begin + '\n' + '\n'.join(added) + '\n' + end + '\n'


def install(backup):
    if os.geteuid() != 0:
        raise RuntimeError('Run via sudo after the installer idle check')
    states = {}
    for unit in UNITS:
        props = run('systemctl', 'show', unit, '-p', 'LoadState', '-p', 'ActiveState', '-p', 'Id').stdout
        values = dict(line.split('=', 1) for line in props.splitlines() if '=' in line)
        # Skip aliases so chrony and chronyd do not count as two services.
        if values.get('Id', unit) != unit:
            continue
        states[unit] = (values.get('LoadState') == 'loaded', values.get('ActiveState') == 'active')
    unit = select_provider(states)
    backup.mkdir(parents=True, exist_ok=True)
    if unit is None:
        # Scoped signed Debian repository; never install a second NTP provider.
        release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
        codename = release.get('VERSION_CODENAME', '').strip('"')
        if codename not in ('bullseye', 'bookworm', 'trixie'):
            raise RuntimeError('Unsupported OS for automatic NTP installation: ' + codename)
        with tempfile.TemporaryDirectory(prefix='lugoware-time-') as tmp:
            os.chmod(tmp, 0o755)
            source = Path(tmp) / 'sources.list'
            source.write_text('deb https://deb.debian.org/debian ' + codename + ' main\n')
            source.chmod(0o644)
            options = ['-o', 'Dir::Etc::sourcelist=' + str(source), '-o', 'Dir::Etc::sourceparts=-',
                       '-o', 'Acquire::Retries=3', '-o', 'APT::Update::Error-Mode=any']
            run('apt-get', *options, 'update')
            run('apt-get', *options, 'install', '-y', '--no-install-recommends', 'systemd-timesyncd')
        unit = 'systemd-timesyncd.service'
    if unit == 'systemd-timesyncd.service':
        path = Path('/etc/systemd/timesyncd.conf.d/90-lugoware.conf')
    elif unit.startswith('chrony'):
        path = next((p for p in (Path('/etc/chrony/chrony.conf'), Path('/etc/chrony.conf')) if p.is_file()), None)
    else:
        path = Path('/etc/ntpsec/ntp.conf' if unit == 'ntpsec.service' else '/etc/ntp.conf')
    if path is None or (unit != 'systemd-timesyncd.service' and not path.is_file()):
        raise RuntimeError('NTP configuration missing; existing service preserved')
    old = path.read_text() if path.exists() else ''
    updated = config_text(unit, old)
    if path.exists():
        shutil.copy2(path, backup / 'ntp-config.before')
    path.parent.mkdir(parents=True, exist_ok=True)
    if old != updated:
        path.write_text(updated)
    run('systemctl', 'enable', unit)
    if old != updated or not states.get(unit, (False, False))[1]:
        run('systemctl', 'restart', unit)
    run('systemctl', 'is-active', unit)
    synchronized = False
    for _ in range(10):
        if run('timedatectl', 'show', '-p', 'NTPSynchronized', '--value').stdout.strip() == 'yes':
            synchronized = True
            break
        time.sleep(2)
    print('[시간 동기화] 부팅 자동 시작: ' + unit, flush=True)
    print('[시간 동기화] ' + ('동기화 확인 완료' if synchronized else '동기화 대기 중: 인터넷/NTP UDP 123 연결을 확인하세요. 동기화 완료로 간주하지 않습니다.'), flush=True)
    (backup / 'status.txt').write_text(run('timedatectl', 'status').stdout)


if __name__ == '__main__':
    import sys
    install(Path(sys.argv[1]))
