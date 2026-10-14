# LUGOWARE Printer Configuration Auto-Update System

## 2026-10-13 M5P Screen and Print Control Update

Existing machines must **run `install.sh` again after printing has finished**. These configurations require the new `fast_cancel.py`; do not apply them first using only the model configuration update button. The last selected screen language is preserved. Subsequent model updates validate the current macros without rewriting model coordinates.

This release includes the final V2.128 M/L/W configurations, CFG-based cancellation, parking and return moves, PAUSE/RESUME state guards and Z limits, and pausing after a failed dock. W docking and parking X coordinates are 104 mm larger than M/L. It also fixes the pause button appearance and removes the long preparation docking-failure notification.

KlipperScreen popups and M117 status messages follow the selected language. Message catalogs cover 32 languages; some translations are machine-generated and may need wording review. Mainsail and raw logs are unchanged.

The installer installs four shared panels from `panels/common` and backs up the existing files. Translations follow the KlipperScreen language setting. Panel updates require running `install.sh`.

Installation and subsequent model updates apply shared templates for screen menus, preheat presets, and the `printer.cfg` header. Device MCU connections, the G-code directory, the complete `SAVE_CONFIG` block, and screen language/theme are preserved. Previous files are backed up. Other custom header settings are replaced by the shared configuration; keep personal tuning in `printer_custom.cfg`.

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
6. Enter the password: `biqu`.

### Step 4 — Run the Installation Command

After connecting via SSH, **copy and paste (right-click)** the command below and press Enter:

```bash
bash <(curl -sSL https://raw.githubusercontent.com/LUGOWARE/lugoware_printer_cfg_update/main/install.sh)
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

When the completion message appears, restart **Klipper** and **Moonraker** in Mainsail.

---

## Subsequent Updates (After Installation)

In Mainsail, go to **Machine** → **Update Manager**, then\
click the **Update button** for **lugoware_config**.

---

## Files That Are Updated

| File | Description |
|------|-------------|
| `printer_base.cfg` | Base printer configuration (motion, heaters, macros, etc.) |
| `crowsnest.conf` | Webcam configuration |
| `KlipperScreen.conf` | Touchscreen configuration |

## Files That Are Not Updated (Protecting Your Settings)

| File | Description |
|------|-------------|
| `printer.cfg` | Printer-specific settings (including the MCU serial and SAVE_CONFIG) |
| `printer_custom.cfg` | Personal tuning values (pressure advance, etc.) |
| `moonraker.conf` | Moonraker server configuration |
| `mainsail.cfg` | Mainsail UI configuration |

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

The extrusion panel uses MVS (mm³/s). Defaults are 10 for 1.75 mm filament, 5 for 2.85 mm filament, and 15 mm of actual filament travel. These values reset when you enter the menu. The arrows adjust values in increments of 1. A check mark identifies the selected diameter, and the Extrude and Retract buttons are at the bottom. The previous distance and speed presets are not used.

## Version display

The top-right corner shows the version from the `printer_base.cfg` header instead of the clock. For example, `# FLEX4_M_V2.128-1` displays `V2.128`, while `# FLEX4_M_V2.18.2` displays `V2.18.2`. File changes are checked about once per second. An unreadable or missing version displays `V—`. Suffixes such as `-1` and `-beta.1` are omitted on screen.

Future releases use `major.minor.patch`: major for substantial hardware-support or configuration-compatibility changes, minor for screen or motion feature changes, and patch for bug fixes and small text or layout adjustments. Existing version numbers are not automatically converted. Board and model identifiers remain separate.
