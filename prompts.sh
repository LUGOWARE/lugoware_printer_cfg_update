#!/bin/bash
# Apply just the screen patch, without firmware or other service changes.
set -euo pipefail
if [[ $EUID -eq 0 ]]; then
    echo '일반 SSH 사용자로 실행하세요.' >&2
    exit 1
fi
COMMON_DIR=$(mktemp -d)
trap 'rm -rf -- "$COMMON_DIR"' EXIT
git clone --quiet --depth 1 --branch main https://github.com/LUGOWARE/lugoware_printer_cfg_update.git "$COMMON_DIR/repo"
bash "$COMMON_DIR/repo/maintenance/apply_prompts.sh"
