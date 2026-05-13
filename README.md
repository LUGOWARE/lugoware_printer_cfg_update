# LUGOWARE 프린터 설정 자동 업데이트 시스템

이 저장소는 LUGOWARE FLEX4 3D 프린터의 설정 파일을 자동으로 업데이트하기 위한 시스템입니다.  
Mainsail 화면에서 버튼 하나로 최신 설정을 받아올 수 있습니다.

> **지원 모델**  
> - **FLEX4 M**
> - **FLEX4 L**
> - **FLEX4 W**

---


<img width="818" height="282" alt="image" src="https://github.com/user-attachments/assets/11c165f2-297a-465b-8b20-bbab5925df4e" />

Mainsail 업데이트 관리자에 lugoware_config 목록이 있다면 설치하지 않으셔도 됩니다.

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
프린터 모델을 선택하세요:
  1) FLEX4 M
  2) FLEX4 L
  3) FLEX4 W

번호 입력 (1/2/3):
```

본인 프린터 모델에 맞는 번호를 입력하고 Enter를 누르면 자동으로 설치가 완료됩니다.

완료 메시지가 뜨면 Mainsail에서 **Klipper**와 **Moonraker**를 재시작해 주세요.

---

## 이후 업데이트 방법 (설치 완료 후)

Mainsail 화면 우측 상단 → **업데이트 관리자** 패널에서  
**lugoware_config** 항목의 **업데이트 버튼** 클릭

자동으로 최신 설정이 적용됩니다.

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
| `printer.cfg` | 프린터별 고유 설정 (SAVE_CONFIG 포함) |
| `printer_custom.cfg` | 개인 튜닝 값 (pressure advance 등) |
| `moonraker.conf` | Moonraker 서버 설정 |
| `mainsail.cfg` | Mainsail UI 설정 |

---

## 문제 해결

**업데이트 후 Klipper가 시작되지 않는 경우**  
SSH 접속 후 아래 명령어를 복사 붙여넣기하여 펌웨어 업데이트 진행

Klipper 펌웨어 소스 코드가 있는 폴더로 이동하여 펌웨어 설정 화면을 엽니다.
```
cd klipper
make menuconfig
```
<img width="702" height="182" alt="1" src="https://github.com/user-attachments/assets/2d5e778a-62bf-4ae7-878a-d18a5e4599e5" />
<img width="346" height="107" alt="2" src="https://github.com/user-attachments/assets/59467b26-5418-4592-8139-46bc12e92d2d" />
사진과 같이 설정을 하고 Q -> Y를 눌러 적용합니다.

설정한 내용을 바탕으로 펌웨어 파일을 컴파일(제작)합니다.
```
make
```
제작된 펌웨어를 프린터 메인보드에 업로드합니다.
```
make flash FLASH_DEVICE=/dev/ttyACM0
```
프린터를 재시작하여 새 펌웨어를 적용합니다.
```
sudo reboot
```

**업데이트 버튼이 보이지 않는 경우**  
설치가 완료되지 않은 것입니다. 4단계 명령어를 다시 실행해 주세요.

**기타 문의**  
LUGOWARE 고객지원으로 연락해 주세요.
