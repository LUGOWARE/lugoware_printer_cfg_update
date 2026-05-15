#!/bin/bash
set -e

FIRMWARE_URL="https://raw.githubusercontent.com/LUGOWARE/lugoware_printer_cfg_update/main/klipper.bin"
FIRMWARE_PATH="/tmp/klipper.bin"

echo "=== LUGOWARE 펌웨어 업데이트 ==="
echo ""

# 펌웨어 다운로드
echo "[1/4] 펌웨어 다운로드 중..."
curl -sSL "$FIRMWARE_URL" -o "$FIRMWARE_PATH"
echo "  -> 다운로드 완료"

# Klipper 서비스 중지
echo "[2/4] Klipper 중지 중..."
sudo service klipper stop
echo "  -> 중지 완료"

# 펌웨어 복사 및 플래시
echo "[3/4] 펌웨어 플래시 중..."
cp "$FIRMWARE_PATH" ~/klipper/out/klipper.bin
cd ~/klipper
make flash FLASH_DEVICE=/dev/ttyACM0
echo "  -> 플래시 완료"

# 재부팅
echo "[4/4] 재부팅 중..."
echo ""
echo "============================================"
echo "  펌웨어 업데이트 완료! 재부팅합니다."
echo "============================================"
echo ""
sudo reboot
