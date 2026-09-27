# LUGOWARE 프린터 설정 자동 업데이트 시스템

## 재설치 및 버전 정책

`install.sh` 성공 후 Moonraker 설정과 활성 include 파일의 klipper / KlipperScreen / mainsail-config 업데이트 항목을 백업 후 주석 처리하고 Moonraker를 재시작합니다. 단, Klipper는 Moonraker 내장 자동 등록 항목이므로 설정 주석만으로 업데이트 창에서 사라지는 것은 보장되지 않습니다. 해당 내장 항목 숨김은 설치된 Moonraker 코드 확인 후 별도 처리가 필요합니다. M5P 배포 바이너리는 이번 변경에서 교체하지 않으며 최종 READY를 검증합니다.

- v0.13.0-770 미만 Klipper는 기존 커밋·변경사항·설정·CB2 실행 파일을 백업하고 배포 기준 `ce7002bedf37e938bb483572949f3703ac6476cb`로 전환합니다. Python 의존성과 Linux(CB2) MCU도 빌드·설치합니다. 알려진 `multi_pin.py` 수정은 보존하며 다른 추적 파일 수정이 있으면 덮어쓰지 않고 중단합니다.
- v0.13.0-770 이상은 본체 버전을 유지합니다. 중단된 Linux MCU 설치가 기록돼 있으면 이어서 진행합니다. 전체 OS 업그레이드는 하지 않습니다.
- READY 상태에서 실제 M5P 버전이 배포본과 같으면 업로드를 건너뜁니다. v0.13 이상에서 이미 정상 연결된 다른 M5P 펌웨어도 보존하고 최종 READY를 확인합니다. READY를 확인하지 못한 경우에는 자동 생략하지 않습니다.
- 동일한 패널·설정, 히터 확장과 자동 복원 구성, cron, 로고 보호, prompts 패치는 다시 설치하지 않습니다. 파일 비교 및 실행 상태 검증은 계속 수행하며 서비스 재시작은 발생할 수 있습니다.
- Bullseye 구형 이미지의 비활성 binary 저장소/폐기된 backports 문제를 피하도록 본체 업그레이드의 빌드 패키지는 임시 공식 binary 저장소 목록을 사용합니다. 기존 APT 설정 파일은 변경하지 않습니다.
- 위 동작은 공통 유지보수 단계에 연결되어 `flash.sh`에도 적용됩니다. 실기기 설치 결과는 완료 시 READY 검증으로 확인해야 합니다.

`flash.sh`는 적용 완료 단계에서 `~/printer_data/config/moonraker.conf`의 `[update_manager KlipperScreen]` 항목 전체를 주석 처리합니다. 수정 전 파일을 설치 백업 폴더에 보관하고, 변경 시 Moonraker를 재시작합니다. 다른 업데이트 항목은 유지합니다.

설치 시 선택한 언어에 맞춰 `panels/ko` 또는 `panels/en`의 `extrude.py`, `nozzle_temperature.py`, `tool_prepare.py`를 `~/KlipperScreen/panels`에 설치합니다. 기존 파일은 설치 백업 폴더의 `panels`에 보관한 뒤 덮어씁니다. 설치 결과에 파일 3개를 표시하고 KlipperScreen을 재시작합니다. 다른 설치 경로는 `KLIPPERSCREEN_DIR`로 지정할 수 있습니다. 패널 배포는 `install.sh` 실행 시 수행되며, 모델 설정의 post-merge 업데이트만으로는 변경되지 않습니다.

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

실행하면 프린터 모델과 언어를 선택하는 메뉴가 나타납니다:

```
프린터 모델을 선택하세요 / Select printer model:
  1) FLEX4 M
  2) FLEX4 L
  3) FLEX4 W

번호 입력 (1/2/3):

언어를 선택하세요 / Select language:
  1) 한국어
  2) English

번호 입력 / Enter number (1/2):
```

본인 프린터 모델과 언어에 맞는 번호를 입력하고 Enter를 누르면 자동으로 설치가 완료됩니다.

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
