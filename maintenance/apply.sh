#!/bin/bash
# Run by install.sh after the model configuration has been installed.
set -euo pipefail
ASSET_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
KLIPPER_DIR=${KLIPPER_DIR:-"$HOME/klipper"}
BACKUP_DIR=${BACKUP_DIR:-"$HOME/lugoware_backups/$(date +%Y%m%d-%H%M%S)-$$"}
export BACKUP_DIR KLIPPER_DIR

if [[ $EUID -eq 0 ]]; then
    echo '일반 SSH 사용자로 실행하세요. 필요한 작업에만 sudo를 사용합니다.' >&2
    exit 1
fi
test -f "$KLIPPER_DIR/klippy/extras/multi_pin.py"
command -v python3 >/dev/null
command -v systemctl >/dev/null
command -v crontab >/dev/null
command -v dfu-util >/dev/null
test -f "$KLIPPER_DIR/scripts/flash_usb.py"
test -c "${FLASH_DEVICE:-/dev/ttyACM0}"
python3 "$ASSET_DIR/verify_firmware.py" "$ASSET_DIR/../firmware"
sudo -v
systemctl cat KlipperScreen.service >/dev/null
sudo python3 "$ASSET_DIR/logo_guard.py" check

# Refuse to stop Klipper during a print, pause, or active heating.
# A Klipper error state is allowed so firmware mismatch can be repaired.
python3 "$ASSET_DIR/check_idle.py"
if [[ ${1:-} == --check ]]; then
    exit 0
fi

mkdir -p "$BACKUP_DIR"
cp -p "$KLIPPER_DIR/klippy/extras/multi_pin.py" "$BACKUP_DIR/multi_pin.py"
python3 - "$ASSET_DIR/multi_pin.py" <<'PY'
import ast, pathlib, sys
ast.parse(pathlib.Path(sys.argv[1]).read_text())
PY

# Back up cron before changing anything. Never erase an unreadable crontab.
if sudo LC_ALL=C crontab -l > "$BACKUP_DIR/root.crontab" 2> "$BACKUP_DIR/cron.stderr"; then
    :
elif ! grep -qi 'no crontab for' "$BACKUP_DIR/cron.stderr"; then
    cat "$BACKUP_DIR/cron.stderr" >&2
    exit 1
fi
python3 - "$BACKUP_DIR/root.crontab" "$BACKUP_DIR/root.crontab.new" <<'PY'
import pathlib, re, sys
source, dest = map(pathlib.Path, sys.argv[1:])
lines = source.read_text().splitlines()
# Replace only this exact recurring task, preserving all unrelated jobs.
pattern = r'^\s*0\s+\*/6\s+\*\s+\*\s+\*\s+/(?:usr/)?bin/systemctl\s+restart\s+KlipperScreen(?:\.service)?\s*(?:#.*)?$'
lines = [line for line in lines if not re.match(pattern, line)]
lines.append('0 */6 * * * /bin/systemctl restart KlipperScreen')
dest.write_text('\n'.join(lines) + '\n')
PY

was_active=0
systemctl is-active --quiet klipper && was_active=1
sudo systemctl stop klipper
# An interrupted/failed installation leaves Klipper stopped, with backups intact.
trap 'echo "적용 실패: Klipper는 중지 상태입니다. 백업: $BACKUP_DIR" >&2' ERR
install -m 644 "$ASSET_DIR/multi_pin.py" "$KLIPPER_DIR/klippy/extras/multi_pin.py.lugoware-new"
mv -f "$KLIPPER_DIR/klippy/extras/multi_pin.py.lugoware-new" "$KLIPPER_DIR/klippy/extras/multi_pin.py"
sudo crontab "$BACKUP_DIR/root.crontab.new"
sudo python3 "$ASSET_DIR/logo_guard.py" install
bash "$ASSET_DIR/flash_firmware.sh"

if [[ $was_active == 1 ]]; then
    sudo systemctl start klipper
    # Connection errors after startup should be visible for diagnosis.
    trap - ERR
    python3 "$ASSET_DIR/wait_ready.py"
fi
trap - ERR
echo "펌웨어, 히터 테스트 확장, 6시간 간격 KlipperScreen 재시작 설정 적용 완료. 백업: $BACKUP_DIR"
