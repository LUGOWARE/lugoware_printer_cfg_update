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
echo '설정 적용이 완료되었습니다.'
