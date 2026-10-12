#!/bin/bash
set -euo pipefail
# Font dependencies only; do not upgrade system packages.
missing=()
for package in fonts-noto-core fonts-noto-cjk; do
    if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -qx 'install ok installed'; then
        missing+=("$package")
    fi
done
if (( ${#missing[@]} )); then
    echo '[진행] 다국어 표시 글꼴 설치 / Installing multilingual fonts'
    options=()
    . /etc/os-release
    if [[ ${VERSION_CODENAME:-} == bullseye ]]; then
        workdir=$(mktemp -d)
        trap 'rm -rf -- "$workdir"' EXIT
        chmod 755 "$workdir"
        printf '%s\n' 'deb https://deb.debian.org/debian bullseye main' > "$workdir/sources.list"
        options=(-o "Dir::Etc::sourcelist=$workdir/sources.list" -o 'Dir::Etc::sourceparts=-')
    fi
    sudo apt-get "${options[@]}" update
    sudo apt-get "${options[@]}" install -y --no-install-recommends "${missing[@]}"
else
    echo '[건너뜀] 다국어 글꼴: 이미 설치됨'
fi
fc-cache -f
if [[ -z $(fc-list :lang=zh-cn family) || -z $(fc-list :lang=zh-tw family) ]]; then
    echo '중국어 글꼴 확인 실패 / Chinese font coverage unavailable' >&2
    exit 1
fi
