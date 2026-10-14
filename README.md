# LUGOWARE 프린터 설정 자동 업데이트 시스템

## M5P 설치 및 업데이트 관리 안내

🌐 [English](README_EN.md) | 한국어

이 저장소는 LUGOWARE FLEX4 3D 프린터의 설정 파일을 자동으로 업데이트하기 위한 시스템입니다.  
Mainsail 화면에서 버튼 하나로 최신 설정을 받아올 수 있습니다.

> **지원 모델**  
> - **FLEX4 M**
> - **FLEX4 L**
> - **FLEX4 W**

---

## 최초 설치 방법 (처음 한 번만)

### 1단계 — MobaXterm 설치

1. [https://mobaxterm.mobatek.net/download.html](https://mobaxterm.mobatek.net/download.html) 접속
2. **MobaXterm Home Edition** → **Installer edition** 다운로드
3. 설치 후 실행

### 2단계 — 프린터 IP 확인

Mainsail 웹 화면 좌측 상단 또는 KlipperScreen 화면에서 프린터 IP를 확인합니다.  
예) `192.168.0.39`

### 3단계 — SSH 접속

1. MobaXterm 실행
2. 상단 **Session** 버튼 클릭
3. **SSH** 선택
4. 아래와 같이 입력:
   - Remote host: `프린터 IP` (예: `192.168.0.39`)
   - Username: `biqu`
   - Port: `22`
5. **OK** 클릭
6. 현재 SSH 비밀번호 입력 (초기 비밀번호를 변경하지 않았다면 `biqu`)

### 4단계 — 설치 명령어 실행

SSH 접속 후 아래 명령어를 **복사해서 붙여넣기(마우스 오른쪽 클릭)** 하고 Enter:

```bash
bash <(curl -fsSL "https://raw.githubusercontent.com/LUGOWARE/lugoware_printer_cfg_update/main/install.sh?nocache=$(date +%s)")
```

실행하면 프린터 모델을 선택하는 메뉴가 나타납니다:

```
프린터 모델을 선택하세요 / Select printer model:
  1) FLEX4 M
  2) FLEX4 L
  3) FLEX4 W

번호 입력 (1/2/3):

```

본인 프린터 모델에 맞는 번호를 입력하고 Enter를 누르면 자동으로 설치가 완료됩니다.

일반 SSH 사용자로 실행하고 sudo 암호 요청에 응답하세요.
프린터를 사용하지 않는 상태에서 진행해 주세요.

설치 과정에서 필요한 서비스를 자동으로 재시작하고 검증합니다. **설치 완료 메시지까지 기다린 뒤** Mainsail을 새로고침하세요. 별도 재시작은 필요하지 않습니다.

- 이 명령은 M5P용입니다. M8P에는 해당 보드 전용 배포판을 사용하세요.
- `main`은 최신 설치 파일을 가리키고, `nocache`는 이전 파일이 캐시에서 내려오는 것을 피합니다. 예전에 안내받은 특정 커밋 주소를 계속 사용할 필요는 없습니다.
- 최초 설치는 sudo 비밀번호가 필요합니다. 설치 중 업데이트 전용 제한 권한을 등록하며, 이후 허용된 Mainsail 업데이트에는 비밀번호 입력이 필요하지 않습니다.
- 기존 설치에 `lugoware_system`이 없다면 위 명령으로 한 번 재설치하세요.

---

## 이후 업데이트 방법 (설치 완료 후)

1. 출력·일시정지·가열·이동 작업이 끝난 상태에서 진행합니다. 설치 중에는 프린터를 사용하거나 전원을 끄지 마세요.
2. Mainsail의 **프린터 설정(Machine) → 업데이트 관리자(Update Manager)**에서 업데이트 확인을 새로고침합니다.
3. 아래 표에 따라 업데이트 항목을 선택합니다.
4. **실제 설치 및 검증 완료** 표시까지 기다립니다.

| 항목 | 적용 내용 | 선택 기준 |
|------|-----------|-----------|
| `lugoware_config` | 모델별 최신 `printer_base.cfg`, `KlipperScreen.conf` | 설정·매크로만 변경된 경우 |
| `lugoware_system` | 화면 패널·번역·Python 확장·공통 설치 기능 및 **해당 모델의 최신 config** | 시스템 변경이 있거나 두 항목 모두 업데이트가 있는 경우 |

**system을 업데이트하면 config도 함께 최신으로 적용되므로 config를 따로 누를 필요가 없습니다.** config만 업데이트하는 기능은 그대로 사용할 수 있습니다. 새 설정이 새 시스템 기능을 요구하면 system부터 업데이트해야 합니다.

### 진행 상황과 완료 확인

업데이트는 Git 다운로드 후 별도 설치 작업으로 이어집니다.

- **다운로드 완료 — 실제 설치 진행 중**: 파일을 받은 상태이며, 아직 설치 완료가 아닙니다.
- **설치 대기 중 / 설치 진행 중**: 업데이트 창과 Mainsail 알림에서 현재 단계를 확인합니다.
- **업데이트 완료 — 실제 설치 및 검증 완료**: config 적용 및 서비스 검증까지 끝난 상태입니다.
- **설치 실패 — 업데이트 미완료**: 원인을 해결한 후 재시도해야 합니다.

설치 중 Moonraker 재시작으로 잠깐 연결이 끊길 수 있습니다. 다시 연결되면 알림을 확인하세요. 이전 표시 기능이 설치된 기기는 다운로드 창에 `Update Finished`가 먼저 보일 수 있으므로, 이번 system 업데이트의 설치 완료 알림을 확인하세요.

필요하면 SSH에서 실제 결과와 상세 로그를 확인할 수 있습니다.

```bash
cat ~/.local/share/lugoware/system-status.json
tail -n 80 ~/printer_data/logs/lugoware_system.log
```

config 단독 업데이트는 위 경로의 `system`을 `config`로 바꾸면 됩니다. 상태 파일의 `state`가 `complete`여야 실제 설치 완료입니다. 실패 원인을 해결한 뒤 Mainsail 서비스 제어에서 `lugoware_system` 또는 `lugoware_config`를 재시작하면 재시도할 수 있습니다.

## 설정 파일과 개인 설정 관리

| 대상 | 업데이트 처리 |
|------|---------------|
| `printer_base.cfg` | 모델별 배포 설정으로 교체됩니다. 직접 수정한 값은 다음 업데이트에서 바뀔 수 있습니다. |
| `KlipperScreen.conf` | 배포 템플릿을 적용하며 마지막 언어 등 보존 대상 사용자 설정을 유지합니다. |
| `printer_custom.cfg` | 기존 파일을 유지합니다. 개인 설정은 적용 가능한 항목을 이 파일에서 관리하세요. |
| `printer.cfg` | 최초 설치·system 업데이트에서 공통 헤더를 정리합니다. 기기 MCU 정보와 기존 SAVE_CONFIG를 보존하며, probe 오프셋이 없으면 기본값 `0.000`을 사용합니다. |
| `moonraker.conf` | 업데이트 항목 등 설치에 필요한 부분을 수정합니다. 파일 전체가 변경되지 않는다는 뜻은 아닙니다. |
| `crowsnest.conf` | 최초 설치·system 업데이트에서 배포본을 적용합니다. config 단독 업데이트 대상은 아닙니다. |

config 단독 업데이트는 `printer_base.cfg`와 `KlipperScreen.conf` 두 파일만 적용합니다. 설치 백업은 `~/lugoware_backups/`에 저장됩니다. `~/lugoware_config` 또는 `~/lugoware_system` 저장소에 직접 수정한 내용이 있으면 자동으로 덮어쓰지 않고 중단하므로, 변경 사항을 별도로 보관하고 정리한 뒤 재시도하세요.

## SSH 재설치가 필요한 경우

일반적인 설정·화면·번역·기존 확장 기능 업데이트는 Mainsail에서 진행합니다. 관리자 권한이 필요한 작업도 **미리 허용된 서비스 제어·지정 패키지·지정 파일 설치**에 한해 비밀번호 없이 실행합니다. 모든 관리자 명령을 허용하는 방식은 아닙니다.

다음 변경은 위 **최초 설치 명령**을 SSH에서 다시 실행하고 sudo 비밀번호를 입력해야 합니다.

- Klipper 본체·Linux MCU 기반 버전 변경
- 구형 Moonraker의 서비스·의존성 구조 변경
- 관리자용 업데이트 helper, sudo 권한 정책 또는 업데이트 서비스 구조 변경
- 허용 목록에 없는 패키지나 새로운 관리자 작업 추가

Mainsail 업데이트에서 SSH 설치가 필요하다는 오류가 나오면 권한을 임의로 확대하지 말고 위 설치 명령으로 진행하세요.

---

## 문제 해결

**업데이트 후 Klipper가 시작되지 않는 경우**  
구버전 펌웨어는 클리퍼에 연결이 되지 않는 경우가 있습니다.  
SSH에 접속하여 아래 명령어를 입력하면 해결됩니다.

```bash
bash <(curl -sSL https://raw.githubusercontent.com/LUGOWARE/lugoware_printer_cfg_update/main/flash.sh)
```

비밀번호 입력: biqu

새 스크립트는 Klipper 서비스를 다시 시작하므로 운영체제 재부팅은 하지 않습니다.

**업데이트 버튼이 보이지 않는 경우**  
설치가 완료되지 않은 것입니다. 4단계 명령어를 다시 실행해 주세요.

**펌웨어 업데이트 후 X축 모터가 반대로 이동하는 경우**  
초기 버전 기기는 모터의 방향이 반대로 설계되어서 최신 펌웨어를 적용할 경우 모터가 반대로 도는 현상이 있습니다.  
Mainsail의 printer_base.cfg에서 [stepper_x] 목록의 dir_pin: PB1을 !PB1 로 변경하여 저장 후 재시작 합니다.  
<img width="817" height="222" alt="image" src="https://github.com/user-attachments/assets/bf1903b1-2865-4c0d-a740-3951755f05b6" />

---

**기타 문의**  
LUGOWARE 고객지원으로 연락해 주세요.
