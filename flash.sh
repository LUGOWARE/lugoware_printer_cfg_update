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
bash "$COMMON_DIR/repo/maintenance/apply.sh"
