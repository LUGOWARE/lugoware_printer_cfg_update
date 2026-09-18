#!/bin/bash
set -euo pipefail
ASSET_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
TARGET="${KLIPPERSCREEN_DIR:-$HOME/KlipperScreen}/ks_includes/widgets/prompts.py"
result=$(python3 "$ASSET_DIR/patch_prompts.py" "$TARGET")
python3 -m py_compile "$TARGET"
if [[ $result == changed ]]; then
    sudo systemctl restart KlipperScreen
    systemctl is-active --quiet KlipperScreen
    echo 'prompts.py 패치·문법 검사·KlipperScreen 재시작 완료'
else
    echo 'prompts.py 이미 적용됨 — 문법 검사 완료, 재시작 생략'
fi
