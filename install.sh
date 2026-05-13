#!/bin/bash
set -e
CONFIG_DIR="$HOME/printer_data/config"
REPO_DIR="$HOME/lugoware_config"
REPO_URL="https://github.com/LUGOWARE/lugoware_printer_cfg_update.git"

echo "=== LUGOWARE 설정 업데이트 시스템 설치 ==="
echo ""

# 모델 선택
echo "프린터 모델을 선택하세요:"
echo "  1) FLEX4 M"
echo "  2) FLEX4 L"
echo "  3) FLEX4 W"
echo ""
read -p "번호 입력 (1/2/3): " model_choice </dev/tty

case $model_choice in
    1) BRANCH="FLEX4_M"; MODEL="FLEX4 M" ;;
    2) BRANCH="FLEX4_L"; MODEL="FLEX4 L" ;;
    3) BRANCH="FLEX4_W"; MODEL="FLEX4 W" ;;
    *) echo "잘못된 입력입니다. 1, 2, 3 중에 선택해 주세요."; exit 1 ;;
esac

echo ""
echo "선택된 모델: $MODEL (브랜치: $BRANCH)"
echo ""

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
cp -f "$REPO_DIR/printer_base.cfg" "$CONFIG_DIR/printer_base.cfg"
cp -f "$REPO_DIR/crowsnest.conf"   "$CONFIG_DIR/crowsnest.conf"
cp -f "$REPO_DIR/KlipperScreen.conf" "$CONFIG_DIR/KlipperScreen.conf"
echo "Config files updated from repo."
EOF
chmod +x "$REPO_DIR/.git/hooks/post-merge"

# 3. printer.cfg 분리 (기존 고객 - 아직 분리 안 된 경우만)
echo "[3/6] printer.cfg 확인 중..."
if ! grep -q "include printer_base.cfg" "$CONFIG_DIR/printer.cfg" 2>/dev/null; then
    echo "  -> printer.cfg 분리 중..."
    python3 - << 'PYEOF'
import os
CONFIG_DIR = os.path.expanduser("~/printer_data/config")
content = open(f"{CONFIG_DIR}/printer.cfg").read()
idx = content.find('#*# <---')
save_config = content[idx:] if idx != -1 else ''
new_cfg = "[include printer_base.cfg]\n[include printer_custom.cfg]\n\n" + save_config
open(f"{CONFIG_DIR}/printer.cfg", 'w').write(new_cfg)
print("  -> printer.cfg 분리 완료")
PYEOF
else
    echo "  -> 이미 분리됨, 건너뜀"
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
cp -f "$REPO_DIR/printer_base.cfg"    "$CONFIG_DIR/printer_base.cfg"
cp -f "$REPO_DIR/crowsnest.conf"      "$CONFIG_DIR/crowsnest.conf"
cp -f "$REPO_DIR/KlipperScreen.conf"  "$CONFIG_DIR/KlipperScreen.conf"
echo "  -> 복사 완료"

# 6. moonraker.conf 업데이트
echo "[6/6] moonraker.conf 업데이트 중..."
BRANCH_VAR="$BRANCH"
python3 - << PYEOF
import re, os
branch = os.environ.get('BRANCH_VAR', '$BRANCH_VAR')
path = os.path.expanduser("~/printer_data/config/moonraker.conf")
content = open(path).read()
# 기존 lugoware_config 섹션 제거 후 새로 추가
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
echo "  설치 완료! 모델: $MODEL"
echo "============================================"
echo ""
echo "다음 단계:"
echo "  Mainsail에서 Klipper와 Moonraker를 재시작해 주세요."
echo ""
echo "  이후 업데이트: Mainsail > 업데이트 매니저 > lugoware_config 업데이트 버튼"
echo ""
