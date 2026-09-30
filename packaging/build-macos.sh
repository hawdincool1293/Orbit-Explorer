#!/bin/bash
set -euo pipefail
[[ "$(uname -s)" == Darwin ]] || { echo 'Run this build on macOS; DMG/PKG cannot be produced by this Linux build.'; exit 1; }
cd "$(dirname "${BASH_SOURCE[0]}")/.."
command -v hdiutil >/dev/null
command -v pkgbuild >/dev/null
python3 -m PyInstaller --noconfirm --distpath build-macos/dist --workpath build-macos/work packaging/Orbit.spec
app="$PWD/build-macos/dist/Orbit.app"
arch="$(uname -m)"
stage="$(mktemp -d "$PWD/build-macos/dmg-stage.XXXXXX")"
# Optional identities must be configured by the owner of the signing account.
if [[ -n "${ORBIT_MAC_APP_IDENTITY:-}" ]]; then
    codesign --force --deep --options runtime --timestamp --sign "$ORBIT_MAC_APP_IDENTITY" "$app"
fi
cp -R "$app" "$stage/Orbit.app"
ln -s /Applications "$stage/Applications"
hdiutil create -volname 'Orbit Explorer' -srcfolder "$stage" -ov -format UDZO "build-macos/Orbit-Explorer-0.6.6-$arch.dmg"
if [[ -n "${ORBIT_MAC_INSTALLER_IDENTITY:-}" ]]; then
    pkgbuild --component "$app" --install-location /Applications --identifier io.github.orbitexplorer.Orbit --version 0.6.6 --sign "$ORBIT_MAC_INSTALLER_IDENTITY" "build-macos/Orbit-Explorer-0.6.6-$arch.pkg"
else
    pkgbuild --component "$app" --install-location /Applications --identifier io.github.orbitexplorer.Orbit --version 0.6.6 "build-macos/Orbit-Explorer-0.6.6-$arch.pkg"
fi
echo 'Built local unsigned/ad-hoc artifacts unless signing identities were supplied.'
echo 'Notarize and staple signed distributions with your own Apple Developer account before public distribution.'
