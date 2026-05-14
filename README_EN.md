# LUGOWARE Printer Config Auto-Update System

🌐 [한국어](README.md) | English

This repository provides an automatic configuration update system for LUGOWARE FLEX4 3D printers.  
Get the latest settings with a single button click in Mainsail.

> **Supported Models**  
> - **FLEX4 W** — Branch: `FLEX4_W`  
> - **FLEX4 M** — Branch: `FLEX4_M`  
> - **FLEX4 L** — Branch: `FLEX4_L`

---

## Initial Installation (One-time Setup)

### Step 1 — Install MobaXterm

1. Go to [https://mobaxterm.mobatek.net/download.html](https://mobaxterm.mobatek.net/download.html)
2. Download **MobaXterm Home Edition** → **Installer edition**
3. Install and launch

### Step 2 — Find Your Printer IP

Check the printer IP on the top-left of the Mainsail web UI or on the KlipperScreen display.  
Example: `192.168.0.39`

### Step 3 — Connect via SSH

1. Launch MobaXterm
2. Click **Session** at the top
3. Select **SSH**
4. Enter the following:
   - Remote host: `Printer IP` (e.g. `192.168.0.39`)
   - Username: `biqu`
   - Port: `22`
5. Click **OK**
6. Enter password: `biqu`

### Step 4 — Run the Installation Command

After connecting via SSH, **copy and paste** the command below and press Enter:

```bash
bash <(curl -sSL https://raw.githubusercontent.com/LUGOWARE/lugoware_printer_cfg_update/main/install.sh)
```

The installer will prompt you to select your printer model and language:

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

Enter the number for your printer model and preferred language, then press Enter. Installation will complete automatically.

Once you see the completion message, restart **Klipper** and **Moonraker** in Mainsail.

---

## How to Update (After Installation)

Go to the top-right of Mainsail → **Update Manager** panel  
Click the **Update** button next to **lugoware_config**

That's it. The latest configuration will be applied automatically.

---

## Files That Get Updated

| File | Description |
|------|-------------|
| `printer_base.cfg` | Base printer config (motion, heaters, macros, etc.) |
| `crowsnest.conf` | Webcam settings |
| `KlipperScreen.conf` | Touchscreen settings |

## Files That Are NOT Updated (Personal Settings Protected)

| File | Description |
|------|-------------|
| `printer.cfg` | Printer-specific settings (MCU serial, SAVE_CONFIG) |
| `printer_custom.cfg` | Personal tuning values (pressure advance, etc.) |
| `moonraker.conf` | Moonraker server settings |
| `mainsail.cfg` | Mainsail UI settings |

---

## Troubleshooting

**Klipper won't start after update**  
Connect via SSH and check the log:
```bash
journalctl -u klipper -n 50
```

**Update button is not visible**  
Installation may not have completed. Run the Step 4 command again.

**Other inquiries**  
Please contact LUGOWARE customer support.
