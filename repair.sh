#!/bin/bash
set -euo pipefail
if [[ $EUID -eq 0 ]]; then
    echo '일반 SSH 사용자로 실행하세요.' >&2
    exit 1
fi
COMMON_DIR=$(mktemp -d)
trap 'rm -rf -- "$COMMON_DIR"' EXIT
git clone --quiet --depth 1 --branch main https://github.com/LUGOWARE/lugoware_printer_cfg_update.git "$COMMON_DIR/repo"
export KLIPPER_DIR=${KLIPPER_DIR:-"$HOME/klipper"}
BACKUP_DIR="$HOME/lugoware_backups/$(date +%Y%m%d-%H%M%S)-repair-$$"
mkdir -m 700 -p "$BACKUP_DIR"
sudo -v
echo '설정을 점검하고 있습니다...'
if bash "$COMMON_DIR/repo/maintenance/repair_multi_pin.sh" "$BACKUP_DIR" >> "$BACKUP_DIR/install.log" 2>&1; then
    echo '설정 복구 및 동작 확인이 완료되었습니다.'
else
    echo "복구 확인에 실패했습니다. 기록: $BACKUP_DIR/install.log" >&2
    exit 1
fi
