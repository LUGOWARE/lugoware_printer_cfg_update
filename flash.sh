#!/bin/bash
# Backward-compatible firmware + maintenance entry point, without cfg split.
set -euo pipefail
if [[ $EUID -eq 0 ]]; then
    echo 'Run as the normal SSH user, without sudo bash.' >&2
    exit 1
fi
COMMON_DIR=$(mktemp -d)
trap 'rm -rf -- "$COMMON_DIR"' EXIT
git clone --depth 1 --branch main \
    https://github.com/LUGOWARE/lugoware_printer_cfg_update.git "$COMMON_DIR/repo"
export BACKUP_DIR="$HOME/lugoware_backups/$(date +%Y%m%d-%H%M%S)-$$"
mkdir -m 700 -p "$BACKUP_DIR"
sudo -v
echo '설정을 적용하고 있습니다. 완료될 때까지 전원을 유지해 주세요...'
if ! bash "$COMMON_DIR/repo/maintenance/apply.sh" >> "$BACKUP_DIR/install.log" 2>&1; then
    echo "설정 적용에 실패했습니다. 고객지원에 문의해 주세요. 기록: $BACKUP_DIR/install.log" >&2
    exit 1
fi
echo 'Moonraker의 KlipperScreen 업데이트 항목을 주석 처리합니다...'
result=$(python3 "$COMMON_DIR/repo/maintenance/disable_screen_updates.py" \
    "$HOME/printer_data/config/moonraker.conf" "$BACKUP_DIR/moonraker.conf")
if [[ $result == changed ]]; then
    sudo systemctl restart moonraker
    systemctl is-active --quiet moonraker
    echo "[완료] KlipperScreen 업데이트 주석 처리 및 Moonraker 재시작 (백업: $BACKUP_DIR/moonraker.conf)"
else
    echo '[확인] moonraker.conf에 활성 KlipperScreen 업데이트 항목이 없습니다.'
fi
echo '설정 적용이 완료되었습니다.'
