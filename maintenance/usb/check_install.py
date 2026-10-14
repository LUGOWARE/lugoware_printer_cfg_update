"""Read-only USB migration check for the restricted Mainsail updater."""
from pathlib import Path


FILES = {
    'usb_udev.sh': '/boot/scripts/usb_udev.sh',
    'usb-mount@.service': '/etc/systemd/system/usb-mount@.service',
    '99-lugoware-usb.rules': '/etc/udev/rules.d/99-lugoware-usb.rules',
}


def current(source, root=Path('/')):
    for name, destination in FILES.items():
        try:
            if (root / destination.lstrip('/')).read_bytes() != (source / name).read_bytes():
                return False
        except OSError:
            return False
    legacy = root / 'etc/udev/rules.d/15-udev.rules'
    try:
        return not legacy.exists() or not any(
            'usb-mount@' in line and not line.lstrip().startswith('#')
            for line in legacy.read_text().splitlines())
    except OSError:
        return False


if __name__ == '__main__':
    if current(Path(__file__).resolve().parent):
        print('[확인 완료] USB 고정 폴더 및 중복 방지 설치됨', flush=True)
    else:
        print('[USB 적용 보류] USB 서비스·udev 설치에는 관리자 권한이 필요합니다. '
              '최신 SSH 설치 명령을 한 번 실행하세요. 이번 Mainsail 업데이트는 '
              '기존 USB 설정을 유지하고 나머지 기능을 적용합니다.', flush=True)
