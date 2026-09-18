# 통합 설치 및 펌웨어 배포

## 구현된 부분

- main/install.sh가 main의 공통 유지보수 파일을 임시 폴더로 받아 실행합니다.
  모델 설정은 기존처럼 FLEX4_M / FLEX4_L / FLEX4_W에서 가져옵니다.
- 기존 설정 폴더, multi_pin.py, root crontab을
  ~/lugoware_backups/날짜-시간-PID에 백업합니다.
- 로컬 Moonraker로 출력/일시정지/가열 여부를 확인합니다.
  확인에 실패하면 중단하고, 펌웨어 불일치를 수리할 수 있도록 Klipper의
  error/shutdown 상태는 허용합니다.
- multi_pin.py를 설치하고, 기존에 실행 중이던 Klipper만 다시 시작합니다.
- firmware/firmware.bin의 체크섬, STM32G0B1 USB 식별 정보, 벡터 주소를
  확인한 뒤 /dev/ttyACM0의 M5P에 업로드합니다.
  `make flash`가 사용하는 `scripts/flash_usb.py`를 직접 호출하므로
  다운로드한 바이너리가 빌드 과정에서 다른 파일로 바뀌지 않습니다.
  MCU는 stm32g0b1, 플래시 시작 주소는 0x08002000 (8 KiB 부트로더)입니다.
- 다시 시작한 Klipper가 60초 안에 READY인지 확인합니다. 실패 시 오류를
  출력하며 설치 성공으로 표시하지 않습니다. 원래 중지된 서비스는 중지 상태를 유지합니다.
- root crontab에 아래 작업을 중복 없이 등록합니다.

```cron
0 */6 * * * /bin/systemctl restart KlipperScreen
```

프린터의 로컬 시간 기준 매일 00:00, 06:00, 12:00, 18:00입니다.
보드/운영체제 전체 재부팅이 아닌 화면 서비스 재시작입니다.

## 히터 테스트

FLEX4_M/L/W의 현재 설정 이름은 dual_hotend_heater입니다.
모드 1은 설정의 첫 핀, 모드 2는 두 번째 핀을 사용합니다.
전환하기 전에 히터 목표 온도를 모두 꺼야 합니다.

```gcode
TURN_OFF_HEATERS
SET_MULTI_PIN_MODE PIN=dual_hotend_heater MODE=1
```

전환 후 원하는 온도를 별도로 설정합니다. 반대쪽 테스트는 MODE=2,
정상 복귀는 히터를 끈 뒤 MODE=0입니다. Klipper가 재시작되면 MODE=0으로
초기화됩니다. 이 확장은 출력 선택 기능이며 자동 합격/불합격 판정은 하지 않습니다.

## 새 펌웨어 배포

1. 검증한 M5P USB 펌웨어를 Windows의
   `C:\Users\nns30\screen\LugoWare Cfg Update\firmware.bin`에 넣습니다.
2. 이 저장소에서 `python maintenance/prepare_firmware.py`를 실행합니다.
   다른 경로는 첫 번째 인수로 지정할 수 있습니다.
3. 생성된 firmware/firmware.bin 및 firmware/firmware.sha256을 함께
   GitHub main에 커밋/푸시합니다. Windows 폴더에 넣기만 해서는 배포되지 않습니다.
4. 프린터에서 기존 main/install.sh 명령을 다시 실행합니다.

현재 포함한 바이너리는 `v0.13.0-745-gf0892d82b-dirty-20260918_100904-bigtreetech-cb2`입니다.
Klipper 호스트 소스 자체를 최신 버전으로 업데이트하거나, CB2 Linux MCU를
재빌드하는 작업은 포함하지 않습니다. 고정된 바이너리가 이후 모든 Klipper
버전과 호환되는 것은 아니므로 버전 변경 시 호환 펌웨어를 다시 배포해야 합니다.
실제 보드에서의 USB 업로드와 각 히터 출력은 최초 한 대에서 확인해야 합니다.

현재 Mainsail의 post-merge 훅은 기존 설정 파일만 갱신합니다.
위 유지보수 단계는 SSH에서 main/install.sh를 다시 실행할 때 적용됩니다.
Klipper 자체 업데이트로 multi_pin.py가 바뀌는 경우에도 다시 적용해야 합니다.
기존 flash.sh 주소도 새 펌웨어와 유지보수 단계를 실행하도록 연결했습니다.
이 진입점은 printer.cfg 분리 작업은 수행하지 않으며 운영체제를 재부팅하지 않습니다.

업로드 실패 시 Klipper를 중지한 채 종료하고 백업 위치를 출력합니다.
USB 재연결이나 부트로더 복구가 필요할 수 있으며, 실제 MCU의 기존 펌웨어를
읽어서 백업하는 기능은 없습니다. 백업 klipper.bin은 디스크에 있던 파일입니다.

## 로컬 검증

```bash
bash -n install.sh
bash -n maintenance/apply.sh
python3 -m unittest discover -s tests -v
```
