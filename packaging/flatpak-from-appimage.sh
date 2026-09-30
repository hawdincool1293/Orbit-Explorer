#!/usr/bin/env bash
# Package the supplied, already-frozen AppImage without rebuilding Python/Qt.
set -euo pipefail
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || { echo 'Use Linux x86-64.'; exit 1; }
[[ $# == 1 && -f "$1" ]] || { echo "Usage: $0 /path/to/Orbit-Explorer-0.6.6-x86_64.AppImage"; exit 1; }
command -v flatpak >/dev/null || { echo 'Install Flatpak first.'; exit 1; }
command -v python3 >/dev/null
image="$(realpath "$1")"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stage="$(mktemp -d "$root/flatpak-package.XXXXXX")"
cd "$stage"
"$image" --appimage-extract
python3 "$root/packaging/stage-linux.py" "$stage/squashfs-root/usr/lib/orbit" "$stage/build"
flatpak build-finish "$stage/build/flatpak"
flatpak build-export "$stage/repo" "$stage/build/flatpak"
flatpak build-bundle "$stage/repo" "$stage/Orbit-Explorer-0.6.6-x86_64.flatpak" \
  io.github.orbitexplorer.Orbit --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo
echo "Created: $stage/Orbit-Explorer-0.6.6-x86_64.flatpak"
echo 'Staging files are retained beside the bundle for inspection.'
