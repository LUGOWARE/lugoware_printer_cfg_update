# LUGOWARE Printer Configuration Auto-Update System

## 2026-10-13 M5P Screen and Print Control Update

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
