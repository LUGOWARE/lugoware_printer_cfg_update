# LUGOWARE 프린터 설정 자동 업데이트 시스템

## 2026-10-13 M5P 화면·출력 제어 업데이트

기존 기기도 **출력이 끝난 뒤 `install.sh`를 다시 실행**해야 합니다. 이번 설정은 새 `fast_cancel.py`와 함께 설치해야 하므로 모델 설정 업데이트 버튼만으로 먼저 적용하지 마세요. 마지막 화면 언어는 유지됩니다. 이후 모델 설정 업데이트는 최신 매크로를 검증하며 모델별 좌표를 다시 쓰지 않습니다.

M·L·W 최종 V2.128 설정, CFG로 분리한 취소·파킹·복귀 동작, PAUSE/RESUME 상태 검사와 Z 상한 제한, 도킹 실패 시 일시정지를 반영했습니다. W의 도킹·파킹 X 좌표는 M/L보다 104mm 큽니다. 화면의 일시정지 버튼 표시를 보정하고 준비 메뉴의 긴 도킹 실패 알림은 제거했습니다.

KlipperScreen의 팝업과 M117 상태 문구도 선택 언어에 맞춰 표시합니다. 32개 언어의 메시지 번역을 포함하며 일부는 기계 번역이므로 표현 검토가 필요할 수 있습니다. Mainsail과 원본 로그는 변경하지 않습니다.

공통 `panels/common`의 패널 4개를 설치하고 기존 파일을 백업합니다. 번역은 KlipperScreen 언어 설정을 따릅니다. 패널 업데이트는 `install.sh`를 실행해야 합니다.

설치와 이후 모델 업데이트는 공통 템플릿의 화면 메뉴·예열 설정과 `printer.cfg` 헤더를 적용합니다. 기기별 MCU 연결 정보, G-code 저장 경로, `SAVE_CONFIG` 전체 및 화면 언어·테마는 보존합니다. 이전 파일은 백업됩니다. 헤더의 그 밖의 사용자 설정은 공통 구성으로 교체되므로 필요한 개인 튜닝은 `printer_custom.cfg`에서 관리하세요.

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
6. 비밀번호 입력: `biqu`

### 4단계 — 설치 명령어 실행

SSH 접속 후 아래 명령어를 **복사해서 붙여넣기(마우스 오른쪽 클릭)** 하고 Enter:

```bash
bash <(curl -sSL https://raw.githubusercontent.com/LUGOWARE/lugoware_printer_cfg_update/main/install.sh)
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

완료 메시지가 뜨면 Mainsail에서 **Klipper**와 **Moonraker**를 재시작해 주세요.

---

## 이후 업데이트 방법 (설치 완료 후)

Mainsail에서 **프린터 설정** → **업데이트 관리자** 패널에서  
**lugoware_config** 항목의 **업데이트 버튼** 클릭

---

## 업데이트되는 파일

| 파일 | 설명 |
|------|------|
| `printer_base.cfg` | 프린터 기본 설정 (모션, 히터, 매크로 등) |
| `crowsnest.conf` | 웹캠 설정 |
| `KlipperScreen.conf` | 터치스크린 설정 |

## 업데이트되지 않는 파일 (개인 설정 보호)

| 파일 | 설명 |
|------|------|
| `printer.cfg` | 프린터별 고유 설정 (MCU 시리얼, SAVE_CONFIG 포함) |
| `printer_custom.cfg` | 개인 튜닝 값 (pressure advance 등) |
| `moonraker.conf` | Moonraker 서버 설정 |
| `mainsail.cfg` | Mainsail UI 설정 |

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
압출 패널은 MVS(mm³/s) 기준입니다. 기본값은 1.75mm=10, 2.85mm=5, 실제 필라멘트 이동 거리=15mm이며 메뉴 진입 시 초기화됩니다. 화살표는 1씩 조절합니다. 선택 직경은 체크 표시로 구분하고 압출·퇴출 버튼은 맨 아래에 배치합니다. 기존 거리·속도 프리셋은 사용하지 않습니다.

## 화면 버전 표시

오른쪽 상단에는 시간 대신 `printer_base.cfg` 헤더의 버전을 작게 표시합니다. 예를 들어 `# FLEX4_M_V2.128-1`은 `V2.128`, `# FLEX4_M_V2.18.2`는 `V2.18.2`로 표시됩니다. 파일 변경은 약 1초 주기로 확인하며, 버전을 읽을 수 없으면 `V—`로 표시합니다. 접미사(`-1`, `-beta.1` 등)는 화면에서 생략합니다.

향후 버전은 `주버전.부버전.수정버전` 형식을 사용합니다. 큰 하드웨어 대응·설정 호환성 변경은 주버전, 화면·동작 기능 변경은 부버전, 버그·문구·배치 등의 작은 수정은 수정버전을 올립니다. 기존 버전 번호를 자동으로 변환하지 않으며, 보드와 모델은 별도로 관리합니다.
