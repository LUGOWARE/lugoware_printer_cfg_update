#!/bin/bash
set -euo pipefail
[[ $# == 3 && $1 == usb && $2 =~ ^sd[a-z]+[0-9]*$ && $3 =~ ^(add|remove)$ ]] || exit 2
device="/dev/$2"
target=/home/biqu/printer_data/gcodes/usb
state=/run/lugoware-usb-owner
exec 9>/run/lock/lugoware-usb.lock
flock -x 9
[[ ! -L "$target" ]] || { echo 'USB path must not be a symlink' >&2; exit 1; }
source_at_target() { findmnt -rn -M "$target" -o SOURCE || true; }
if [[ $3 == add ]]; then
    [[ -b "$device" ]] || exit 1
    fs=$(blkid -s TYPE -o value "$device")
    current=$(source_at_target)
    if [[ -n "$current" ]]; then
        [[ "$current" == "$device" ]] && exit 0
        echo "USB occupied by $current; leaving $device unmounted"
        exit 0
    fi
    if findmnt -rn -S "$device" >/dev/null; then
        echo "$device already mounted elsewhere; refusing duplicate mount" >&2
        exit 1
    fi
    mkdir -p "$target"
    # Never cover locally uploaded files with a mount.
    [[ -z "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit)" ]] || {
        echo 'USB directory contains local files; not mounting over them' >&2; exit 1;
    }
    uid=$(id -u biqu); gid=$(id -g biqu)
    options="nosuid,nodev,noexec"
    case "$fs" in
        vfat) options+=",iocharset=utf8,uid=$uid,gid=$gid,umask=0022" ;;
        exfat|ntfs) options+=",uid=$uid,gid=$gid,umask=0022" ;;
        ext2|ext3|ext4) ;;
        *) echo "Unsupported USB filesystem: $fs" >&2; rmdir "$target"; exit 1 ;;
    esac
    if ! mount -o "$options" "$device" "$target"; then
        rmdir "$target" || true
        exit 1
    fi
    printf '%s\n' "$device" > "$state"
else
    owner=$(cat "$state" 2>/dev/null || true)
    current=$(source_at_target)
    [[ "$owner" == "$device" || "$current" == "$device" ]] || exit 0
    if [[ -n "$current" ]]; then
        [[ "$current" == "$device" ]] || exit 1
        if ! umount "$target"; then
            # Lazy detach only after physical removal; never detach a live busy drive.
            [[ ! -b "$device" ]] || exit 1
            umount -l "$target"
        fi
    fi
    [[ -z "$(source_at_target)" ]] || exit 1
    [[ ! -d "$target" ]] || rmdir "$target"
    rm -f "$state"
fi
