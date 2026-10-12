## 화면 언어 자동 연동

메뉴 버튼과 화면 제목은 번역 길이에 따라 가운데 정렬로 줄바꿈합니다. 설치 시 `fonts-noto-core`와 `fonts-noto-cjk`를 확인·설치해 중국어 간체/번체 등의 누락 글자를 보완합니다. 시스템 전체 업그레이드는 하지 않으며 최초 글꼴 설치에는 네트워크 연결이 필요합니다. `KlipperScreen`은 프로그램 고유 이름이므로 번역하지 않습니다.

설치 시 언어 선택을 묻지 않으며 KlipperScreen에서 마지막으로 저장한 언어와 사용자 저장 설정을 유지합니다. 설정 → 언어에서 변경하면 기본 화면과 추가 패널, 준비 메뉴, 툴별 온도 제어, 히터 테스트 표시가 해당 언어를 사용합니다. 추가 UI 문구는 현재 지원되는 32개 언어의 오프라인 번역을 제공합니다. 기본 화면은 KlipperScreen 공식 번역을 사용하므로 공식 번역이 없는 문구는 영어로 표시될 수 있습니다. 필라멘트 프로필 이름·파일명·G-code 명령은 원문을 유지합니다.

기존 기기는 아래 설치 명령을 다시 실행해야 다국어 패널이 설치됩니다. 이후 모델 설정 업데이트도 저장된 언어를 유지합니다. 번역 파일과 추가 방법은 [translations/README.md](translations/README.md)를 참고하세요.

# LUGOWARE 프린터 설정 자동 업데이트 시스템

## 2026-10-12 M5P 화면·출력 제어 업데이트

기존 기기도 install.sh를 다시 실행해야 이번 공통 코드가 설치됩니다. M·L·W 모델 모두 적용되며, 설정 언어에 연동되는 공통 패널을 제공합니다. 모델 설정 업데이트 버튼만으로 새 패널이나 Python 확장 코드가 내려오지는 않습니다. 설치 후의 모델 설정 업데이트에는 저장해 둔 패처가 준비·취소 매크로를 다시 적용합니다.

- 출력 화면의 노즐·베드 온도 바로가기는 기본 온도창을 엽니다. 설정 → 툴별 온도 제어에서는 사용 중인 툴만 표시하고 오른쪽 화살표로 1°C씩 조절합니다. 버튼 강조 시간은 0.05초입니다.
- 시작 코드 중 노즐·베드 변경은 별도 API로 처리합니다. 베드 목표 온도가 설정되기 전에는 준비 중으로 표시하고 조절을 차단합니다. 변경한 목표에 맞춰 시작 코드의 온도 대기 범위도 변경합니다.
- 압출 화면에서 필라멘트 직경 선택을 파란색으로 강조하고, 출력/일시정지 중 모터 끄기를 차단합니다.
- 준비 화면에서 다른 자리로 파킹·프라임할 때 빈 자리 확인 창을 표시합니다. 센서가 빈 자리를 자동 판별하는 기능은 아니며, 사용자가 확인해야 합니다.
- KlipperScreen의 출력 취소는 정상 취소 API를 사용합니다. 예열 대기를 종료하고 툴체인지는 기구적으로 안전한 경계까지 마친 뒤 장착 툴을 파킹합니다. 메쉬 중에는 현재 한 번의 프로빙을 마친 뒤 Z를 올려 종료하며 불완전한 메쉬를 저장하지 않습니다. 비상정지를 대체하지 않으며 Mainsail의 취소 경로는 변경하지 않습니다.
- 취소 요청 성공 팝업과 취소 과정의 자동 압출 화면 이동을 없앴습니다. MCU MHz 불일치 팝업만 숨기고 다른 오류 및 로그는 유지합니다.

검증: Python 테스트 167개, M5P 세 모델 매크로 재적용, 기준 KlipperScreen v0.4.7-191 설치/재설치, Jinja 및 셸 문법 검사. 실제 툴 이동·프로빙은 기기에서 확인해야 합니다. 펌웨어 바이너리는 변경하지 않았습니다.

## 재설치 및 버전 정책

현재 추가 자동 업데이트 대상은 Mainsail, print_area_bed_mesh, sonar 3개입니다. Moonraker 및 시스템 패키지 업그레이드는 제외합니다. 구버전 Klipper를 올릴 때 필요한 빌드 의존성 설치는 별도로 유지합니다. 아래 시스템 자동 업데이트 설명은 이전 동작입니다.

최신 변경: Moonraker 자체는 자동 업데이트 대상에서 제외했습니다. 추가 업데이트는 시스템 패키지, Mainsail, print_area_bed_mesh, sonar 4개만 수행하며 이 단계에서 Moonraker 숨김 패치를 원복하지 않습니다. 아래 Moonraker 자체 업데이트 관련 내용은 이전 동작입니다.

`install.sh`는 공통 설치 후 Moonraker API로 시스템 패키지 → Mainsail → print_area_bed_mesh → sonar → Moonraker 순서로 업데이트합니다. 각 항목의 현재 채널(stable/dev 등)에서 제공되는 최신 버전을 사용하며, 버전/커밋과 패키지 수를 새로 조회해 최신 항목은 건너뜁니다. 등록되지 않은 항목은 건너뜀으로 표시합니다. lugoware_config는 기존 모델 브랜치 git pull 단계에서 업데이트합니다. 전체 업데이트 API는 사용하지 않아 Klipper와 커스텀 KlipperScreen은 이 과정에 포함되지 않습니다.

진행 단계, 이전/대상 버전, 대기, 완료/최신 상태를 터미널과 install.log에 표시합니다. Moonraker 소스의 알려진 LUGOWARE 숨김 패치만 백업 후 잠시 원복하고 업데이트 후 재적용합니다. 다른 사용자 수정은 강제 삭제하지 않습니다. 실패 시 전체 설치 완료로 표시하지 않으며, 최신 Moonraker 구조가 패치와 달라지면 확인이 필요합니다. 시스템이 재부팅을 요구하면 안내만 출력하며 자동 재부팅하지 않습니다. OS 배포판 업그레이드는 하지 않습니다.

`install.sh` 성공 후 Moonraker 설정과 활성 include 파일의 klipper / KlipperScreen / mainsail-config 업데이트 항목을 백업 후 주석 처리하고 Moonraker를 재시작합니다. Klipper 내장 자동 등록은 update_manager.py를 백업 후 패치해 차단합니다. 재연결 시 재등록도 차단하며 다른 업데이트 항목은 유지합니다. 설치 마지막에 Moonraker API로 세 항목의 숨김을 검증합니다. Moonraker 자체 업데이트로 코드 패치가 덮어써지면 설치기를 다시 실행해야 합니다. M5P 배포 바이너리는 이번 변경에서 교체하지 않으며 최종 READY를 검증합니다.

- v0.13.0-770 미만 Klipper는 기존 커밋·변경사항·설정·CB2 실행 파일을 백업하고 배포 기준 `ce7002bedf37e938bb483572949f3703ac6476cb`로 전환합니다. Python 의존성과 Linux(CB2) MCU도 빌드·설치합니다. 알려진 `multi_pin.py` 수정은 보존하며 다른 추적 파일 수정이 있으면 덮어쓰지 않고 중단합니다.
- v0.13.0-770 이상은 본체 버전을 유지합니다. 중단된 Linux MCU 설치가 기록돼 있으면 이어서 진행합니다. 전체 OS 업그레이드는 하지 않습니다.
- READY 상태에서 실제 M5P 버전이 배포본과 같으면 업로드를 건너뜁니다. v0.13 이상에서 이미 정상 연결된 다른 M5P 펌웨어도 보존하고 최종 READY를 확인합니다. READY를 확인하지 못한 경우에는 자동 생략하지 않습니다.
- 동일한 패널·설정, 히터 확장과 자동 복원 구성, cron, 로고 보호, prompts 패치는 다시 설치하지 않습니다. 파일 비교 및 실행 상태 검증은 계속 수행하며 서비스 재시작은 발생할 수 있습니다.
- Bullseye 구형 이미지의 비활성 binary 저장소/폐기된 backports 문제를 피하도록 본체 업그레이드의 빌드 패키지는 임시 공식 binary 저장소 목록을 사용합니다. 기존 APT 설정 파일은 변경하지 않습니다.
- 위 동작은 공통 유지보수 단계에 연결되어 `flash.sh`에도 적용됩니다. 실기기 설치 결과는 완료 시 READY 검증으로 확인해야 합니다.

`flash.sh`는 적용 완료 단계에서 `~/printer_data/config/moonraker.conf`의 `[update_manager KlipperScreen]` 항목 전체를 주석 처리합니다. 수정 전 파일을 설치 백업 폴더에 보관하고, 변경 시 Moonraker를 재시작합니다. 다른 업데이트 항목은 유지합니다.

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


## 툴별 출력 온도와 Moonraker 관리

공식 install.sh는 출력 화면의 노즐 온도 버튼을 T1~T4 전용 패널에 연결합니다. Orca G-code의 filament_settings_id에서 저장된 프로필 이름을 표시하고, 툴별로 수정한 온도는 이번 출력의 툴체인지 이후에도 유지합니다. 종료·취소·새 출력·Klipper 재시작 시 초기화됩니다. 현재 공통 패널은 온도 오른쪽 화살표로 1°C씩 조절합니다.

G-code에 프로필 이름이 없으면 소재 종류로 대체하며, 읽을 정보가 없으면 Unknown으로 표시합니다. 기존 도킹의 일시적 추가 예열은 유지하므로 수정 온도 상한은 extruder max_temp보다 40℃ 낮습니다. 별도 SET_HEATER_TEMPERATURE 명령은 재정의하지 않습니다.

출력 중 더보기의 온도 항목은 통합 툴 온도 패널에 연결하고 카메라·핀 항목은 숨깁니다. 설정 파일과 패널은 설치 백업에 보관됩니다. 이후 모델 설정 업데이트 시에도 메뉴 숨김을 다시 적용합니다.

Moonraker 구버전은 검증된 v0.11.0-0 커밋(68db047aa9189248800904531f6354d8fd76d8eb)으로 업데이트하며, 이미 해당 버전 이상이면 유지합니다. 최신 버전을 무조건 받거나 상위 버전을 다운그레이드하지 않습니다. 설치 후 Moonraker는 Klipper·KlipperScreen·mainsail-config와 함께 업데이트 관리자에서 숨겨집니다. 이 정책은 install.sh를 다시 실행한 기기에 적용됩니다.

출력 화면의 노즐·베드 온도 버튼은 같은 툴별 온도 패널로 연결됩니다. 베드의 현재/목표 온도를 표시하며 기본 키패드로 베드 목표를 수정할 수 있습니다(일반 M140 동작). 파일 전체의 START_PRINT INITIAL_TOOL, CHANGE_TOOL NEXT_TOOL, T0~T3 명령을 조사해 사용하지 않는 툴은 없음으로 표시하고 비활성화합니다. 임의 매크로 내부에서만 툴이 선택되는 경우 실제 CHANGE_TOOL 실행 시 목록에 추가됩니다.

메인 화면 상단은 화면을 열 때마다 현재 IP를 조회해 표시합니다. IP 조회가 불가능하면 IP —로 표시합니다. 공통 압출 메뉴의 모서리 압출제어 버튼은 제거됩니다.

압출 패널은 MVS(mm³/s) 기준입니다. 기본값은 1.75mm=10, 2.85mm=5, 실제 필라멘트 이동 거리=15mm이며 메뉴 진입 시 초기화됩니다. 화살표는 1씩 조절합니다. 선택 직경은 체크 표시로 구분하고 압출·퇴출 버튼은 맨 아래에 배치합니다. 기존 거리·속도 프리셋은 사용하지 않습니다.
