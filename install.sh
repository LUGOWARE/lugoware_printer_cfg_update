#!/bin/bash
set -e
CONFIG_DIR="$HOME/printer_data/config"
REPO_DIR="$HOME/lugoware_config"
REPO_URL="https://github.com/LUGOWARE/lugoware_printer_cfg_update.git"

echo "=== LUGOWARE 설정 업데이트 시스템 설치 ==="
echo ""

# 모델 선택
echo "프린터 모델을 선택하세요 / Select printer model:"
echo "  1) FLEX4 M"
echo "  2) FLEX4 L"
echo "  3) FLEX4 W"
echo ""
read -p "번호 입력 (1/2/3): " model_choice </dev/tty

case $model_choice in
    1) BRANCH="FLEX4_M"; MODEL="FLEX4 M"; MODEL_CODE="HM1" ;;
    2) BRANCH="FLEX4_L"; MODEL="FLEX4 L"; MODEL_CODE="HL1" ;;
    3) BRANCH="FLEX4_W"; MODEL="FLEX4 W"; MODEL_CODE="HW1" ;;
    *) echo "잘못된 입력입니다. 1, 2, 3 중에 선택해 주세요."; exit 1 ;;
esac

echo ""
echo "선택된 모델: $MODEL (브랜치: $BRANCH)"
echo ""

# 언어 선택
echo "언어를 선택하세요 / Select language:"
echo "  1) 한국어"
echo "  2) English"
echo ""
read -p "번호 입력 / Enter number (1/2): " lang_choice </dev/tty

case $lang_choice in
    1) LANG_CODE="ko" ;;
    2) LANG_CODE="en" ;;
    *) echo "잘못된 입력입니다. 1 또는 2를 선택해 주세요."; exit 1 ;;
esac

echo ""
echo "선택된 언어 / Selected language: $LANG_CODE"
echo ""

# 언어 설정 저장
echo "$LANG_CODE" > "$HOME/.lugoware_lang"

# 1. 레포 클론 or 업데이트
if [ -d "$REPO_DIR/.git" ]; then
    echo "[1/6] 기존 레포 업데이트 중..."
    cd "$REPO_DIR"
    git fetch origin
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
else
    echo "[1/6] 레포 클론 중..."
    git clone -b "$BRANCH" "$REPO_URL" "$REPO_DIR"
    cd "$REPO_DIR"
fi

# 2. post-merge 훅 설정
echo "[2/6] post-merge 훅 설정 중..."
cat > "$REPO_DIR/.git/hooks/post-merge" << 'EOF'
#!/bin/bash
CONFIG_DIR="$HOME/printer_data/config"
REPO_DIR="$HOME/lugoware_config"
LANG_CODE=$(cat "$HOME/.lugoware_lang" 2>/dev/null || echo "ko")
cp -f "$REPO_DIR/printer_base.cfg"              "$CONFIG_DIR/printer_base.cfg"
cp -f "$REPO_DIR/crowsnest.conf"                "$CONFIG_DIR/crowsnest.conf"
cp -f "$REPO_DIR/KlipperScreen_${LANG_CODE}.conf" "$CONFIG_DIR/KlipperScreen.conf"
echo "Config files updated from repo. (language: $LANG_CODE)"
EOF
chmod +x "$REPO_DIR/.git/hooks/post-merge"

# 3. printer.cfg 분리
echo "[3/6] printer.cfg 확인 중..."
export MODEL_CODE_VAR="$MODEL_CODE"
if ! grep -q "include printer_base.cfg" "$CONFIG_DIR/printer.cfg" 2>/dev/null; then
    echo "  -> printer.cfg 분리 중..."
    python3 - << 'PYEOF'
import os, re
CONFIG_DIR = os.path.expanduser("~/printer_data/config")
model_code = os.environ.get('MODEL_CODE_VAR', 'HW1')
content = open(f"{CONFIG_DIR}/printer.cfg").read()

# MCU serial 추출
mcu_match = re.search(r'\[mcu\][^\[]*?serial\s*:\s*(\S+)', content, re.DOTALL)
mcu_serial = mcu_match.group(1) if mcu_match else '/dev/serial/by-id/YOUR_MCU_SERIAL'

# SAVE_CONFIG 섹션 추출
save_idx = content.find('#*# <---')
save_config = ('\n' + content[save_idx:]) if save_idx != -1 else ''

new_cfg = (
    f"# ########==========================={model_code}_M5P_MULTISET============================########\n"
    f"# ########============================== MCU 설정 ===============================########\n"
    f"\n"
    f"[include mainsail.cfg]\n"
    f"[include timelapse.cfg]\n"
    f"[include printer_base.cfg]\n"
    f"[include printer_custom.cfg]\n"
    f"\n"
    f"[mcu CB2]\n"
    f"serial: /tmp/klipper_host_mcu\n"
    f"\n"
    f"[mcu]\n"
    f"serial: {mcu_serial}\n"
    f"\n"
    f"[virtual_sdcard]\n"
    f"path: /home/biqu/printer_data/gcodes\n"
    f"{save_config}"
)
open(f"{CONFIG_DIR}/printer.cfg", 'w').write(new_cfg)
print(f"  -> printer.cfg 생성 완료 (MCU: {mcu_serial})")
PYEOF
else
    echo "  -> 이미 분리됨, 건너뜀"
    # 기존 설치 마이그레이션: MCU 섹션이 printer.cfg에 없으면 추가
    python3 - << 'PYEOF'
import os, re
CONFIG_DIR = os.path.expanduser("~/printer_data/config")
model_code = os.environ.get('MODEL_CODE_VAR', 'HW1')
printer_content = open(f"{CONFIG_DIR}/printer.cfg").read()

if '[mcu]' not in printer_content:
    # printer_base.cfg에서 serial 찾기
    base_content = open(f"{CONFIG_DIR}/printer_base.cfg").read()
    mcu_match = re.search(r'\[mcu\][^\[]*?serial\s*:\s*(\S+)', base_content, re.DOTALL)
    mcu_serial = mcu_match.group(1) if mcu_match else '/dev/serial/by-id/YOUR_MCU_SERIAL'

    mcu_block = (
        f"# ########==========================={model_code}_M5P_MULTISET============================########\n"
        f"# ########============================== MCU 설정 ===============================########\n"
        f"\n"
        f"[include mainsail.cfg]\n"
        f"[include timelapse.cfg]\n"
        f"\n"
        f"[mcu CB2]\n"
        f"serial: /tmp/klipper_host_mcu\n"
        f"\n"
        f"[mcu]\n"
        f"serial: {mcu_serial}\n"
        f"\n"
        f"[virtual_sdcard]\n"
        f"path: /home/biqu/printer_data/gcodes\n"
        f"\n"
    )
    open(f"{CONFIG_DIR}/printer.cfg", 'w').write(mcu_block + printer_content)
    print(f"  -> MCU 섹션 추가 완료 (MCU: {mcu_serial})")
else:
    print("  -> MCU 섹션 이미 존재, 건너뜀")
PYEOF
fi

# 4. printer_custom.cfg 없으면 생성
echo "[4/6] printer_custom.cfg 확인 중..."
if [ ! -f "$CONFIG_DIR/printer_custom.cfg" ]; then
    cat > "$CONFIG_DIR/printer_custom.cfg" << 'EOF'
# 이 프린터 전용 설정 파일입니다. 업데이트해도 변경되지 않습니다.
EOF
    echo "  -> printer_custom.cfg 생성 완료"
else
    echo "  -> 이미 존재함, 건너뜀"
fi

# 5. 설정 파일 복사
echo "[5/6] 설정 파일 복사 중..."
cp -f "$REPO_DIR/printer_base.cfg"                    "$CONFIG_DIR/printer_base.cfg"
cp -f "$REPO_DIR/crowsnest.conf"                      "$CONFIG_DIR/crowsnest.conf"
cp -f "$REPO_DIR/KlipperScreen_${LANG_CODE}.conf"     "$CONFIG_DIR/KlipperScreen.conf"
echo "  -> 복사 완료"

# 6. moonraker.conf 업데이트
echo "[6/6] moonraker.conf 업데이트 중..."
BRANCH_VAR="$BRANCH"
python3 - << PYEOF
import re, os
branch = os.environ.get('BRANCH_VAR', '$BRANCH_VAR')
path = os.path.expanduser("~/printer_data/config/moonraker.conf")
content = open(path).read()
content = re.sub(r'\[update_manager lugoware_config\][\s\S]*?(?=\[|\Z)', '', content).rstrip()
content += f"""

[update_manager lugoware_config]
type: git_repo
path: ~/lugoware_config
origin: https://github.com/LUGOWARE/lugoware_printer_cfg_update.git
primary_branch: {branch}
is_system_service: False
managed_services: klipper
"""
open(path, 'w').write(content)
print(f"  -> moonraker.conf 업데이트 완료 (브랜치: {branch})")
PYEOF

echo ""
echo "============================================"
echo "  설치 완료! 모델: $MODEL / 언어: $LANG_CODE"
echo "============================================"
echo ""
echo "다음 단계:"
echo "  Mainsail에서 Klipper와 Moonraker를 재시작해 주세요."
echo ""
echo "  이후 업데이트: Mainsail > 업데이트 매니저 > lugoware_config 업데이트 버튼"
echo ""
