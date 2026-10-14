# LUGOWARE Printer Configuration Auto-Update System

## M5P Installation and Update Management

🌐 English | [한국어](README.md)

This repository provides a system for automatically updating configuration files for LUGOWARE FLEX4 3D printers.\
You can download the latest configuration with a single button in Mainsail.

> **Supported models**\
> - **FLEX4 M**
> - **FLEX4 L**
> - **FLEX4 W**

---

## Initial Installation (Once Only)

### Step 1 — Install MobaXterm

1. Visit [https://mobaxterm.mobatek.net/download.html](https://mobaxterm.mobatek.net/download.html).
2. Download **MobaXterm Home Edition** → **Installer edition**.
3. Install and launch it.

### Step 2 — Find the Printer's IP Address

Find the printer's IP address in the upper-left corner of the Mainsail web interface or on the KlipperScreen display.\
Example: `192.168.0.39`

### Step 3 — Connect via SSH

1. Launch MobaXterm.
2. Click **Session** at the top.
3. Select **SSH**.
4. Enter the following:
   - Remote host: `Printer IP` (for example, `192.168.0.39`)
   - Username: `biqu`
   - Port: `22`
5. Click **OK**.
6. Enter your current SSH password (`biqu` if the initial password has not been changed).

### Step 4 — Run the Installation Command

After connecting via SSH, **copy and paste (right-click)** the command below and press Enter:

```bash
bash <(curl -fsSL "https://raw.githubusercontent.com/LUGOWARE/lugoware_printer_cfg_update/main/install.sh?nocache=$(date +%s)")
```

A menu will appear asking you to select your printer model:

```
Select printer model:
  1) FLEX4 M
  2) FLEX4 L
  3) FLEX4 W

Enter number (1/2/3):

```

Enter the number corresponding to your printer model and press Enter. Installation will complete automatically.

Run the command as your regular SSH user and enter your sudo password when prompted.
Proceed while the printer is not in use.

The installer restarts and checks the required services automatically. **Wait for the installation completion message**, then refresh Mainsail. No additional restart is required.

- This command is for M5P. Use the dedicated distribution for an M8P board.
- Initial installation requires your sudo password. It registers restricted update permissions so subsequent supported Mainsail updates do not prompt for a password.
- If an existing installation has no `lugoware_system` entry, run the command above once to reinstall.

---

## Subsequent Updates (After Installation)

1. Finish any print, pause, heating or movement operation first. Do not use or power off the printer during installation.
2. In Mainsail, open **Machine → Update Manager** and refresh the update check.
3. Select an update using the table below.
4. Wait for **actual installation and verification completion**.

| Entry | What it applies | When to use it |
|-------|-----------------|----------------|
| `lugoware_config` | Latest model-specific `printer_base.cfg` and `KlipperScreen.conf` | Configuration or macro changes only |
| `lugoware_system` | Screen panels, translations, Python extensions, shared installation features, and **the latest config for your model** | System changes, or updates available for both entries |

**A system update also applies the latest config; a separate config update is not required.** Config-only updates remain available. If a new configuration requires new system features, update system first.

### Progress and completion

Git download is followed by a separate installation job. The current updater uses these Korean status labels:

- **다운로드 완료 — 실제 설치 진행 중**: Download complete; actual installation is still running.
- **설치 대기 중 / 설치 진행 중**: Installation queued / in progress. Check the update dialog and Mainsail announcements for the current stage.
- **업데이트 완료 — 실제 설치 및 검증 완료**: Actual installation, config application and service verification have completed.
- **설치 실패 — 업데이트 미완료**: Installation failed; resolve the cause before retrying.

Moonraker may briefly disconnect while restarting. Check announcements after reconnecting. A device with the previous reporting component may still show `Update Finished` as soon as the download ends; check the actual installation completion announcement for this system update.

For detailed results, these optional SSH commands show the status and log:

```bash
cat ~/.local/share/lugoware/system-status.json
tail -n 80 ~/printer_data/logs/lugoware_system.log
```

For a config-only update, replace `system` with `config` in those paths. The status file must report `state: complete` for actual installation completion. After resolving a failure, restart `lugoware_system` or `lugoware_config` from Mainsail service controls to retry.

## Managing Configuration and Personal Settings

| Item | Update behavior |
|------|-----------------|
| `printer_base.cfg` | Replaced with the model release configuration. Direct edits may be replaced by the next update. |
| `KlipperScreen.conf` | The release template is merged while retaining supported user preferences, including the last selected language. |
| `printer_custom.cfg` | Existing file is preserved. Use it for personal settings where applicable. |
| `printer.cfg` | Initial installation and system updates normalize the common header while preserving device MCU information and existing SAVE_CONFIG. A missing probe offset defaults to `0.000`. |
| `moonraker.conf` | Installation-related sections, including update entries, are modified. The whole file is not guaranteed to remain unchanged. |
| `crowsnest.conf` | Applied from the release during initial installation and system updates; excluded from config-only updates. |

Config-only updates apply just `printer_base.cfg` and `KlipperScreen.conf`. Backups are stored in `~/lugoware_backups/`. Direct edits in the `~/lugoware_config` or `~/lugoware_system` repositories stop the automatic update instead of being overwritten. Save and resolve those changes before retrying.

---

## Troubleshooting

**Klipper does not start after an update**\
Older firmware may fail to connect to Klipper.\
Connect via SSH and run the following command to resolve this:

```bash
bash <(curl -sSL https://raw.githubusercontent.com/LUGOWARE/lugoware_printer_cfg_update/main/flash.sh)
```

Enter the password: `biqu`.

The new script restarts the Klipper service without rebooting the operating system.

**The Update button is not visible**\
Installation has not completed. Run the command in Step 4 again.

**The X-axis motor moves in the opposite direction after a firmware update**\
Early machines were designed with the opposite motor direction, so installing the latest firmware may cause the motor to turn in reverse.\
In Mainsail, open `printer_base.cfg` and change `dir_pin: PB1` to `dir_pin: !PB1` in the `[stepper_x]` section, then save and restart.\
<img width="817" height="222" alt="image" src="https://github.com/user-attachments/assets/bf1903b1-2865-4c0d-a740-3951755f05b6" />

---

**Other Questions**\
Please contact LUGOWARE customer support.
