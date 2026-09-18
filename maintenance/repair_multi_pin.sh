#!/bin/bash
set -euo pipefail
ASSET_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
KLIPPER_DIR=${KLIPPER_DIR:-"$HOME/klipper"}
python3 "$ASSET_DIR/check_idle.py"
cp -p "$KLIPPER_DIR/klippy/extras/multi_pin.py" "$1/multi_pin.py"
sudo systemctl stop klipper
bash "$ASSET_DIR/setup_multi_pin.sh"
sudo systemctl start klipper
python3 "$ASSET_DIR/verify_multi_pin.py" "$KLIPPER_DIR"
