#!/bin/bash
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'USB installation requires root'; exit 1; }
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 - <<'PY'
import json, urllib.request
s=json.load(urllib.request.urlopen('http://127.0.0.1:7125/printer/objects/query?print_stats',timeout=5))['result']['status']['print_stats']['state']
if s not in ('standby','complete','cancelled','error'): raise SystemExit('Printer must be idle: '+s)
PY
bash -n "$root/usb_udev.sh"
backup="${1:-/home/biqu/lugoware_backups/usb-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$backup"
for existing in /boot/scripts/usb_udev.sh /etc/systemd/system/usb-mount@.service /etc/udev/rules.d/15-udev.rules; do
    [[ ! -e "$existing" ]] || cp -a "$existing" "$backup/"
done
if [[ -e /etc/udev/rules.d/99-lugoware-usb.rules ]]; then cp -a /etc/udev/rules.d/99-lugoware-usb.rules "$backup/"; fi
# Stop existing mounts before replacing their cleanup handler. Never force a live unmount.
mapfile -t units < <(systemctl list-units --all --plain --no-legend 'usb-mount@*.service' | awk '{print $1}')
for unit in "${units[@]}"; do systemctl stop "$unit"; done
for folder in /home/biqu/printer_data/gcodes/usb-sd*; do
    [[ -d "$folder" && ! -L "$folder" ]] || continue
    if mountpoint -q "$folder"; then umount "$folder"; fi
    # Empty directories only. Never remove files from local storage or USB.
    rmdir "$folder" || echo "Preserved nonempty directory: $folder"
done
install -d /boot/scripts
install -m 755 "$root/usb_udev.sh" /boot/scripts/usb_udev.sh
install -m 644 "$root/usb-mount@.service" /etc/systemd/system/usb-mount@.service
# Remove only the legacy mount service rules; preserve unrelated vendor rules.
python3 - <<'PY'
from pathlib import Path
p=Path('/etc/udev/rules.d/15-udev.rules')
if p.exists():
    lines=p.read_text().splitlines(keepends=True)
    p.write_text(''.join(line for line in lines if 'usb-mount@' not in line or line.lstrip().startswith('#')))
PY
install -m 644 "$root/99-lugoware-usb.rules" /etc/udev/rules.d/99-lugoware-usb.rules
systemctl daemon-reload
udevadm control --reload-rules
# Mount existing USB filesystem devices without asking the user to reconnect.
for device in /sys/class/block/sd*; do
    [[ -e "$device" ]] || continue
    properties=$(udevadm info --query=property --path="$device")
    if grep -qx 'ID_BUS=usb' <<< "$properties" && grep -qx 'ID_FS_USAGE=filesystem' <<< "$properties"; then
        systemctl restart "usb-mount@$(basename "$device").service"
    fi
done
echo "USB update complete. Backup: $backup"
findmnt -rn -M /home/biqu/printer_data/gcodes/usb || true
