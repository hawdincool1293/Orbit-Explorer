#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
command -v appimagetool >/dev/null || { echo 'Install appimagetool first.'; exit 1; }
command -v flatpak >/dev/null || { echo 'Install flatpak first.'; exit 1; }
python3 -m PyInstaller --noconfirm --distpath build/dist --workpath build/work packaging/Orbit.spec
python3 packaging/stage-linux.py build/dist/Orbit build
ARCH=x86_64 appimagetool build/Orbit.AppDir build/Orbit-Explorer-0.6.6-x86_64.AppImage
flatpak build-finish build/flatpak
flatpak build-export build/repo build/flatpak
flatpak build-bundle build/repo build/Orbit-Explorer-0.6.6-x86_64.flatpak io.github.orbitexplorer.Orbit --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo
