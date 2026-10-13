#!/bin/bash
set -euo pipefail
CONFIG_DIR="$HOME/printer_data/config"
REPO_DIR="$HOME/lugoware_config"
REPO_URL="https://github.com/LUGOWARE/lugoware_printer_cfg_update.git"
copy_config() {
    if cmp -s "$1" "$2"; then
        echo "  [건너뜀] $(basename "$2"): 동일한 설정"
    else
        cp -f "$1" "$2"
    fi
}

if [[ $EUID -eq 0 ]]; then
    echo "일반 SSH 사용자로 실행하세요 (sudo bash 사용 금지)." >&2
    exit 1
fi

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

echo "화면 언어는 KlipperScreen에서 마지막으로 선택한 설정을 유지합니다."

# 공통 기능은 모델 브랜치와 별도로 main에서 같은 커밋으로 가져옵니다.
COMMON_DIR=$(mktemp -d)
trap 'rm -rf -- "$COMMON_DIR"' EXIT
git clone --depth 1 --branch main "$REPO_URL" "$COMMON_DIR/repo"
export BACKUP_DIR="$HOME/lugoware_backups/$(date +%Y%m%d-%H%M%S)-$$"
mkdir -m 700 -p "$BACKUP_DIR"
MOONRAKER_UPDATER="${MOONRAKER_DIR:-$HOME/moonraker}/moonraker/components/update_manager/update_manager.py"
PANEL_DIR="${KLIPPERSCREEN_DIR:-$HOME/KlipperScreen}/panels"
python3 "$COMMON_DIR/repo/maintenance/install_panels.py" --target "$PANEL_DIR" --backup "$BACKUP_DIR/panels" --check
sudo -v
echo "설치 환경을 확인하고 있습니다..."
python3 "$COMMON_DIR/repo/maintenance/upgrade_klipperscreen.py" --check
echo '[확인] 이전 설치에서 중단된 Moonraker 복구'
python3 "$COMMON_DIR/repo/maintenance/upgrade_moonraker.py" --recover-only 2>&1 | tee -a "$BACKUP_DIR/install.log"
python3 "$COMMON_DIR/repo/maintenance/check_idle.py"
cp -a "$CONFIG_DIR" "$BACKUP_DIR/config"

echo '[업데이트 1/6] Klipper 버전 확인 및 업데이트'
python3 -u "$COMMON_DIR/repo/maintenance/upgrade_klipper.py" 2>&1 | tee -a "$BACKUP_DIR/install.log"
echo '[업데이트 2/6] KlipperScreen 버전 확인 및 업데이트'
python3 -u "$COMMON_DIR/repo/maintenance/upgrade_klipperscreen.py" 2>&1 | tee -a "$BACKUP_DIR/install.log"
python3 "$COMMON_DIR/repo/maintenance/install_i18n.py" --check
# Comment configuration now; the built-in Klipper patch needs Moonraker >= 0.11.
python3 "$COMMON_DIR/repo/maintenance/disable_screen_updates.py" \
    "$CONFIG_DIR/moonraker.conf" "$BACKUP_DIR/moonraker-update-sections" --installed-components
echo '[업데이트 3/6] Moonraker 최소 v0.11.0-0 확인 및 업데이트'
python3 -u "$COMMON_DIR/repo/maintenance/upgrade_moonraker.py" 2>&1 | tee -a "$BACKUP_DIR/install.log"
python3 "$COMMON_DIR/repo/maintenance/hide_klipper_updater.py" \
    "$MOONRAKER_UPDATER" "$BACKUP_DIR/update_manager.py"
echo '[확인] sonar 서비스 재시작 권한'
python3 "$COMMON_DIR/repo/maintenance/allow_sonar_service.py" 2>&1 | tee -a "$BACKUP_DIR/install.log"
sudo systemctl restart moonraker
sudo systemctl start klipper
# Klipper may report a firmware mismatch until the later firmware patch stage.
python3 - <<'PY'
import json, time, urllib.request
for attempt in range(90):
    try:
        with urllib.request.urlopen('http://127.0.0.1:7125/printer/info', timeout=5) as response:
            state = json.load(response)['result']['state']
        if state in ('ready', 'error', 'shutdown'):
            break
    except Exception:
        pass
    time.sleep(2)
else:
    raise SystemExit('Klipper 연결 확인 실패: 로그를 확인하세요.')
PY
echo '[업데이트 4~6/6] Mainsail / print_area_bed_mesh / sonar (시스템 전체 업데이트 제외)'
python3 -u "$COMMON_DIR/repo/maintenance/update_components.py" 2>&1 | tee -a "$BACKUP_DIR/install.log"
echo '[업데이트 완료] 설정 파일 및 사용자 패치 적용 시작'
if ! bash "$COMMON_DIR/repo/maintenance/apply.sh" --check >> "$BACKUP_DIR/install.log" 2>&1; then
    echo "설치 환경 확인에 실패했습니다. 고객지원에 문의해 주세요. 기록: $BACKUP_DIR/install.log" >&2
    exit 1
fi
sudo -v


# 1. 레포 클론 or 업데이트
if [ -d "$REPO_DIR/.git" ]; then
    echo "[1/6] 기존 레포 업데이트 중..."
    cd "$REPO_DIR"
    git fetch origin
    # The previous hook may rewrite current macros with legacy commands.
    # This installer applies the configuration after installing current helpers.
    git -c core.hooksPath=/dev/null checkout "$BRANCH"
    git -c core.hooksPath=/dev/null pull --ff-only origin "$BRANCH"
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
for name in printer_base.cfg crowsnest.conf; do
    target="$name"
    if ! cmp -s "$REPO_DIR/$name" "$CONFIG_DIR/$target"; then
        cp -f "$REPO_DIR/$name" "$CONFIG_DIR/$target"
    fi
done
if [[ -f "$HOME/.local/share/lugoware/install_printer_header.py" ]]; then
    python3 "$HOME/.local/share/lugoware/install_printer_header.py" "$HOME/.local/share/lugoware/printer_header.cfg" "$CONFIG_DIR/printer.cfg" "$HOME/lugoware_backups/post-merge-printer-$(date +%Y%m%d-%H%M%S).cfg" || exit 1
fi
if [[ -f "$HOME/.local/share/lugoware/install_screen_config.py" ]]; then
    python3 "$HOME/.local/share/lugoware/install_screen_config.py" "$HOME/.local/share/lugoware/KlipperScreen.conf" "$CONFIG_DIR/KlipperScreen.conf" "$HOME/lugoware_backups/post-merge-screen-$(date +%Y%m%d-%H%M%S).conf" || exit 1
fi
if [[ -f "$HOME/.local/share/lugoware/install_tool_temperature.py" ]]; then
    python3 "$HOME/.local/share/lugoware/install_tool_temperature.py" --config-only || exit 1
fi
if [[ -f "$HOME/.local/share/lugoware/install_print_controls.py" ]]; then
    python3 "$HOME/.local/share/lugoware/install_print_controls.py" --config-only || exit 1
fi
echo "Config files updated from repo. Screen language preserved."
EOF
chmod +x "$REPO_DIR/.git/hooks/post-merge"

# 3. .151 기준 공통 헤더 / 각 기기의 MCU·SAVE_CONFIG 보존
echo "[3/6] printer.cfg 공통 헤더 적용 중..."
python3 "$COMMON_DIR/repo/maintenance/install_printer_header.py" \
    "$COMMON_DIR/repo/templates/printer_header.cfg" "$CONFIG_DIR/printer.cfg" \
    "$BACKUP_DIR/printer-header.cfg" --fallback "$CONFIG_DIR/printer_base.cfg"

# Probe SAVE_CONFIG preservation/defaulting is handled by install_printer_header.py.

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
copy_config "$REPO_DIR/printer_base.cfg" "$CONFIG_DIR/printer_base.cfg"
copy_config "$REPO_DIR/crowsnest.conf" "$CONFIG_DIR/crowsnest.conf"
python3 "$COMMON_DIR/repo/maintenance/install_screen_config.py" \
    "$COMMON_DIR/repo/templates/KlipperScreen.conf" "$CONFIG_DIR/KlipperScreen.conf" "$BACKUP_DIR/KlipperScreen.conf"
echo "  -> 복사 완료"

# 6. moonraker.conf 업데이트
echo "[6/6] moonraker.conf 업데이트 중..."
BRANCH_VAR="$BRANCH"
python3 - << PYEOF
import re, os
branch = os.environ.get('BRANCH_VAR', '$BRANCH_VAR')
path = os.path.expanduser("~/printer_data/config/moonraker.conf")
original = open(path).read()
content = re.sub(r'\[update_manager lugoware_config\][\s\S]*?(?=\[|\Z)', '', original).rstrip()
content += f"""

[update_manager lugoware_config]
type: git_repo
path: ~/lugoware_config
origin: https://github.com/LUGOWARE/lugoware_printer_cfg_update.git
primary_branch: {branch}
is_system_service: False
managed_services: klipper
"""
if content != original:
    open(path, 'w').write(content)
    print(f"  -> moonraker.conf 업데이트 완료 (브랜치: {branch})")
else:
    print('  [건너뜀] moonraker.conf: 동일한 설정')
PYEOF

# 공통 다국어 패널 설치 (기존 파일 백업 후 덮어쓰기)
echo "KlipperScreen 다국어 패널 설치 / Installing multilingual panels"
bash "$COMMON_DIR/repo/maintenance/install_fonts.sh"
python3 "$COMMON_DIR/repo/maintenance/install_i18n.py"
python3 "$COMMON_DIR/repo/maintenance/install_panels.py" --target "$PANEL_DIR" --backup "$BACKUP_DIR/panels"

echo '[진행] 툴별 출력 온도 및 출력 더보기 메뉴 설치'
python3 "$COMMON_DIR/repo/maintenance/install_tool_temperature.py"
echo "[진행] 준비 화면 / 빠른 정상 취소 / 메쉬 중 취소 / MHz 팝업 숨김"
python3 "$COMMON_DIR/repo/maintenance/install_print_controls.py"
echo "[진행] 메인 화면 IP 표시 / 압출 모서리 제어 버튼 제거"
python3 "$COMMON_DIR/repo/maintenance/patch_screen_identity.py"
mkdir -p "$HOME/.local/share/lugoware"
cp "$COMMON_DIR/repo/maintenance/install_printer_header.py" "$COMMON_DIR/repo/templates/printer_header.cfg" "$COMMON_DIR/repo/templates/KlipperScreen.conf" "$HOME/.local/share/lugoware/"
cp "$COMMON_DIR/repo/maintenance/install_tool_temperature.py" "$COMMON_DIR/repo/maintenance/install_screen_config.py" "$HOME/.local/share/lugoware/"
cp "$COMMON_DIR/repo/maintenance/install_print_controls.py" "$COMMON_DIR/repo/maintenance/patch_print_controls.py" "$COMMON_DIR/repo/maintenance/final_print_ui.py" "$HOME/.local/share/lugoware/"

# 공통 시스템 설정 (재실행해도 cron 중복 없음)
echo "설정을 적용하고 있습니다. 완료될 때까지 전원을 유지해 주세요..."
if ! LUGOWARE_SHOW_STATUS=1 bash "$COMMON_DIR/repo/maintenance/apply.sh" 3>&1 >> "$BACKUP_DIR/install.log" 2>&1; then
    echo "설정 적용에 실패했습니다. 고객지원에 문의해 주세요. 기록: $BACKUP_DIR/install.log" >&2
    exit 1
fi

sudo systemctl restart KlipperScreen
systemctl is-active --quiet KlipperScreen
echo "패널 4개 설치 완료 / Installed: extrude.py, nozzle_temperature.py, tool_prepare.py, tool_temperature.py"
echo "패널 백업 / Panel backup: $BACKUP_DIR/panels"

python3 "$COMMON_DIR/repo/maintenance/wait_ready.py" --ready-only
python3 "$COMMON_DIR/repo/maintenance/verify_multi_pin.py" "$HOME/klipper"

# Hide managed components only after all installation checks succeeded.
echo 'Klipper / KlipperScreen / mainsail-config / Moonraker 업데이트 항목 주석 처리 중...'
python3 "$COMMON_DIR/repo/maintenance/hide_klipper_updater.py" \
    "$MOONRAKER_UPDATER" "$BACKUP_DIR/update_manager.py"
updates_result=$(python3 "$COMMON_DIR/repo/maintenance/disable_screen_updates.py" \
    "$CONFIG_DIR/moonraker.conf" "$BACKUP_DIR/moonraker-update-sections" --installed-components)
# Restart even if already commented: an earlier run may have stopped before reload.
sudo systemctl restart moonraker
systemctl is-active --quiet moonraker
echo "[완료] 업데이트 항목 주석 처리 및 Moonraker 재시작 ($updates_result)"
python3 - <<'PY'
import json, time, urllib.request
last = 'Moonraker is starting'
for attempt in range(30):
    try:
        with urllib.request.urlopen('http://127.0.0.1:7125/machine/update/status', timeout=5) as response:
            versions = json.load(response)['result']['version_info']
        remaining = {'klipper', 'klipperscreen', 'mainsail-config', 'moonraker'} & {name.casefold() for name in versions}
        if not remaining:
            print('[확인 완료] klipper / KlipperScreen / mainsail-config / Moonraker 업데이트 항목 숨김')
            break
        last = 'Update entries still present: ' + ', '.join(sorted(remaining))
    except Exception as exc:
        last = str(exc)
    time.sleep(2)
else:
    raise SystemExit('업데이트 항목 숨김 확인 실패: ' + last)
PY

echo ""
echo "============================================"
echo "  설치 완료! 모델: $MODEL / 화면 언어: 기존 설정 유지"
echo "============================================"
echo ""
echo "  이후 업데이트: Mainsail > 업데이트 매니저 > lugoware_config 업데이트 버튼"
echo ""
echo "모든 적용 및 검증이 완료되었습니다. 프린터 전체 재부팅은 하지 않습니다."
