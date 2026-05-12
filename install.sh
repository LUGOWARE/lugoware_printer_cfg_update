#!/bin/bash
CONFIG_DIR="$HOME/printer_data/config"
REPO_DIR="$HOME/lugoware_config"

cp -f "$REPO_DIR/printer_base.cfg" "$CONFIG_DIR/printer_base.cfg"
cp -f "$REPO_DIR/crowsnest.conf" "$CONFIG_DIR/crowsnest.conf"
cp -f "$REPO_DIR/KlipperScreen.conf" "$CONFIG_DIR/KlipperScreen.conf"
