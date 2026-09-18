#!/bin/bash
set -euo pipefail
ASSET_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
KLIPPER_DIR=${KLIPPER_DIR:-"$HOME/klipper"}
sudo install -d -m 755 /opt/lugoware/multi-pin /etc/systemd/system/klipper.service.d
sudo install -m 644 "$ASSET_DIR/multi_pin.py" "$ASSET_DIR/install_multi_pin.py" /opt/lugoware/multi-pin/
python3 - "$KLIPPER_DIR" <<'PY' | sudo tee /etc/systemd/system/klipper.service.d/90-lugoware-extension.conf >/dev/null
import sys
path = sys.argv[1]
if any(char in path for char in '\n\r"\\'):
    raise SystemExit('Unsupported Klipper directory')
path = path.replace('%', '%%').replace('$', '$$')
print('[Service]')
print('ExecStartPre=/usr/bin/python3 /opt/lugoware/multi-pin/install_multi_pin.py "' + path + '"')
PY
sudo systemctl daemon-reload
python3 /opt/lugoware/multi-pin/install_multi_pin.py "$KLIPPER_DIR"
