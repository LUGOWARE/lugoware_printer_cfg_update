#!/bin/bash
# Called with Klipper already stopped by apply.sh.
set -euo pipefail
ASSET_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
KLIPPER_DIR=${KLIPPER_DIR:-"$HOME/klipper"}
FLASH_DEVICE=${FLASH_DEVICE:-/dev/ttyACM0}
python3 "$ASSET_DIR/verify_firmware.py" "$ASSET_DIR/../firmware"
test -c "$FLASH_DEVICE"
mkdir -p "$KLIPPER_DIR/out"
if [[ -f "$KLIPPER_DIR/out/klipper.bin" ]]; then
    cp -p "$KLIPPER_DIR/out/klipper.bin" "${BACKUP_DIR:?}/klipper.bin"
fi
install -m 644 "$ASSET_DIR/../firmware/firmware.bin" "$KLIPPER_DIR/out/klipper.bin"
cd "$KLIPPER_DIR"
# Same uploader as STM32 make flash, without its build dependencies replacing
# the supplied image. M5P: STM32G0B1, USB, 8 KiB bootloader.
python3 "$ASSET_DIR/run_flash.py" python3 scripts/flash_usb.py -t stm32g0b1 -d "$FLASH_DEVICE" \
    -s 0x08002000 out/klipper.bin
echo '전송 단계 완료. 실제 MCU 연결 및 버전을 확인해야 합니다.'
