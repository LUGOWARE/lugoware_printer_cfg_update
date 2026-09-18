#!/bin/bash
# Run by install.sh after the model configuration has been installed.
set -euo pipefail
ASSET_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
KLIPPER_DIR=${KLIPPER_DIR:-"$HOME/klipper"}
BACKUP_DIR=${BACKUP_DIR:-"$HOME/lugoware_backups/$(date +%Y%m%d-%H%M%S)-$$"}
export BACKUP_DIR KLIPPER_DIR
status() {
    echo "$*"
    if [[ ${LUGOWARE_SHOW_STATUS:-0} == 1 ]]; then
        printf '%s\n' "$*" >&3
    fi
}
stage='설치 준비'
trap 'status "[실패] $stage — 상세 내용은 install.log를 확인하세요."' ERR

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
python3 "$ASSET_DIR/patch_prompts.py" "${KLIPPERSCREEN_DIR:-$HOME/KlipperScreen}/ks_includes/widgets/prompts.py" --check
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

sudo systemctl stop klipper
# An interrupted/failed installation leaves Klipper stopped, with backups intact.
stage='히터 테스트 코드 설치'
status '[진행] 히터 테스트 코드 설치 (실행 검증은 재시작 후 진행)'
bash "$ASSET_DIR/setup_multi_pin.sh"
stage='KlipperScreen 재시작 예약'
status '[진행] KlipperScreen 재시작 예약 설정'
sudo crontab "$BACKUP_DIR/root.crontab.new"
sudo crontab -l > "$BACKUP_DIR/root.crontab.verified"
cmp "$BACKUP_DIR/root.crontab.new" "$BACKUP_DIR/root.crontab.verified"
systemctl is-active --quiet cron.service
systemctl is-enabled --quiet cron.service
status '[확인 완료] KlipperScreen: 매일 0·6·12·18시 재시작 예약 및 cron 서비스 확인'
stage='로고 보호'
status '[진행] 로고 보호 설정 및 부팅 이미지 갱신'
sudo python3 "$ASSET_DIR/logo_guard.py" install
sudo python3 "$ASSET_DIR/logo_guard.py" verify
status '[확인 완료] 로고 보호: 백업 일치·자동 복원 등록·부팅 이미지 갱신 완료'
stage='펌웨어 업로드'
status '[진행] 펌웨어 업로드'
bash "$ASSET_DIR/flash_firmware.sh"

sudo systemctl start klipper
# A previous failed attempt may have left the service stopped. Always start it
# after flashing and verify the actual flashed MCU, not just the process state.
stage='펌웨어 연결 및 버전 검증'
status '[검증] Klipper 연결 및 실제 MCU 펌웨어 버전 확인'
python3 "$ASSET_DIR/wait_ready.py" "$ASSET_DIR/../firmware/firmware.bin"
status '[확인 완료] 펌웨어: MCU 버전 일치 및 Klipper READY'
stage='히터 테스트 코드 실행 검증'
python3 "$ASSET_DIR/verify_multi_pin.py" "$KLIPPER_DIR"
status '[확인 완료] 히터 테스트: 파일 일치 및 SET_MULTI_PIN_MODE 명령 등록'
stage='KlipperScreen 여러 줄 안내 패치'
status '[진행] KlipperScreen prompts.py 패치 및 문법 검사'
bash "$ASSET_DIR/apply_prompts.sh"
status '[확인 완료] KlipperScreen: prompt_text 누적 패치 및 문법 검증'
status '※ 실제 히터 출력과 재부팅 화면은 별도 확인이 필요합니다.'
trap - ERR
echo "펌웨어, 히터 테스트 확장, 6시간 간격 KlipperScreen 재시작 설정 적용 완료. 백업: $BACKUP_DIR"
