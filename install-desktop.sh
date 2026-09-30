#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
destination="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$destination"
cat > "$destination/orbit-explorer.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Orbit Explorer
Comment=Spatial file explorer for Linux
Exec=$project_dir/run.sh
Icon=$project_dir/assets/orbit.svg
Terminal=false
Categories=System;FileManager;
StartupNotify=true
EOF
echo "Installed $destination/orbit-explorer.desktop"
