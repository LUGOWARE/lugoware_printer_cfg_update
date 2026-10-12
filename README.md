# LUGOWARE 프린터 설정 자동 업데이트 시스템

## 2026-10-12 M5P 화면·출력 제어 업데이트

기존 기기도 install.sh를 다시 실행해야 이번 공통 코드가 설치됩니다. M·L·W 모델 모두 적용되며, 설정 언어에 연동되는 공통 패널을 제공합니다. 모델 설정 업데이트 버튼만으로 새 패널이나 Python 확장 코드가 내려오지는 않습니다. 설치 후의 모델 설정 업데이트에는 저장해 둔 패처가 준비·취소 매크로를 다시 적용합니다.

공통 `panels/common`의 패널 4개를 설치하고 기존 파일을 백업합니다. 번역은 KlipperScreen 언어 설정을 따릅니다. 패널 업데이트는 `install.sh`를 실행해야 합니다.

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

### KlipperScreen 설치 버전 정책

`install.sh`는 KlipperScreen이 `v0.4.7-191` 미만이면 공식 커밋
`3f08a9f782f3232a205c8004f4c5a681637e2b42`로 업데이트합니다.
같거나 이후 버전은 유지합니다. 버전을 판별할 수 없으면 덮어쓰지 않고 중단합니다.
기존 소스와 변경 내역은 설치 백업 폴더의 `klipperscreen-upgrade`에 저장합니다.
기존 Git 추적 파일의 수정은 stash에 보관하고 공식 소스로 교체하며,
공통 다국어 패널 4개와 prompts 패치는 업데이트 후 다시 적용합니다.
별도로 수정한 코어 파일은 자동 병합하지 않습니다.
Python 의존성 설치가 중단되면 다음 설치에서 재개합니다.
설치 완료 시 KlipperScreen 업데이트 항목은 Moonraker에서 주석 처리되어 숨겨집니다.
설치 순서는 Klipper → KlipperScreen → Moonraker → Mainsail → print_area_bed_mesh → sonar → 사용자 설정·패치입니다.
Moonraker는 `v0.11.0-0` 미만이면 공식 커밋 `68db047aa9189248800904531f6354d8fd76d8eb`로 올리고,
같거나 이후 버전이면 유지합니다. 구버전 Moonraker에는 숨김 코드 패치를 먼저 시도하지 않습니다.
Klipper와 KlipperScreen 설정 항목은 먼저 주석 처리하고, 내장 Klipper 업데이트 항목은 Moonraker 업데이트 후 숨깁니다.
Moonraker 업데이트에는 공식 설치 스크립트의 필수 의존성·서비스 갱신이 포함됩니다.
시스템 전체 업데이트는 실행하지 않습니다.

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
