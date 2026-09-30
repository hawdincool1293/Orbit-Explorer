# Orbit Explorer 0.6.6 — installation and build notes

This update replaces the 0.6.4/0.6.5 bounce with Orbit's original cubic fades.
Settings → Panel animations retains area toggles, duration, fade and file-panel
travel. A new frame-rate target defaults to 120 FPS. Actual displayed FPS depends
on the compositor, screen and workload. Existing durations and area preferences
are preserved; obsolete bounce values no longer affect motion.

## Package status

Linux release artifacts target **x86-64**. The AppImage contains Python, QtPdf,
Qt Multimedia, image codecs, FFmpeg/FFprobe and ripgrep, so it does not depend
on a separately installed PySide6. It was built on Ubuntu 24.04 and requires a
glibc-based distribution with **glibc 2.39 or newer**. CachyOS/current Arch is
the primary target. This is not an ARM or musl/Alpine package.

**This 0.6.6 delivery is the source/update ZIP only.** It combines the attached
0.6.2 source and input/video patches. No new AppImage, Flatpak, DMG or PKG has
been built in this merge. The native package commands below describe the
retained build recipes; build new packages from this patched source. The
Ubuntu/glibc information above describes the earlier 0.6.2 AppImage build.

**Flatpak build blocked here:** the local Flatpak tools fail with `linkat: No
such file or directory` while exporting/creating the repository in this
restricted filesystem. No installable `.flatpak` is supplied. The source ZIP
includes a packaging script that can turn the supplied AppImage into a Flatpak
on a regular Linux machine, without rebuilding Python or Qt (instructions below).

The Flatpak recipe uses the Freedesktop 25.08 runtime to avoid most host-library
differences. A graphical Wayland or X11 session and a supported GPU/audio stack
are still required. A Flatpak is not a promise of compatibility with every
Linux kernel or compositor.
Runtime packaging reference: https://docs.flatpak.org/en/latest/first-build.html

## Updating to 0.6.6 on Niri or another Linux desktop

1. Close all Orbit windows.
2. **AppImage installation:** replace your old AppImage with
   `Orbit-Explorer-0.6.6-x86_64.AppImage`, make it executable, and launch it using
   the commands below. If a launcher points to the old versioned filename,
   update that path or keep the same filename in the same location.
3. **Existing source installation:** use `bash /orbit-explorer/update.sh
   "$HOME/Downloads/Orbit-Explorer-0.6.6.zip"`. This updates the program in place;
   it does not create a nested installation. Preferences and unrelated files
   are preserved, and the updater prints a rollback-backup path.
4. Existing icon preferences are retained. To use the included icons, choose
   **Settings → Icons & previews → Sweet (bundled)**. New settings default to it.
5. Use **Exact** beside either search field, or **Settings → Controls → Strict
   search**, for complete case-sensitive filenames (including extensions).

The graph now renders at the display's pixel ratio and uses real background
alpha. Change **Settings → Appearance → Window opacity** to test transparency.
Native Wayland is preferred if WAYLAND_DISPLAY is set; explicit platform
overrides remain respected. If your launcher forces XWayland, test:

```bash
QT_QPA_PLATFORM=wayland ./Orbit-Explorer-0.6.6-x86_64.AppImage
```

The reported Python `eventFilter` exception is fixed. Orbit now also uses the
packaged desktop ID `io.github.orbitexplorer.Orbit`. A remaining
`Connection already associated with an application ID` message is a separate
host Qt/portal registration warning; it is not evidence that the Python fix
failed. Niri's compositor and your portal session cannot be exercised here.
If crashes remain, start Orbit in a terminal and retain the full output plus
the action immediately preceding the crash. Do not delete your settings to
apply this update.

macOS service adapters and a **native macOS build script** are included. The
macOS port has not been built or tested on a Mac in this workspace. No DMG/PKG
should be considered delivered or validated until that script runs on macOS.
Qt 6.11 supports macOS 13+, covering Sequoia 15 and Tahoe 26:
https://doc.qt.io/qt-6/supported-platforms.html

## Niri transparency and Fontconfig warnings in 0.6.5

Niri normally may draw a solid border/focus-ring rectangle behind a window with
client-side decorations. This can mask the desktop even when Orbit is painting
transparent pixels. Add this **top-level** block to your existing
`~/.config/niri/config.kdl` (do not replace the whole config):

```kdl
window-rule {
    match app-id="^io[.]github[.]orbitexplorer[.]Orbit$"
    draw-border-with-background false
}
```

Run `niri validate` and restart Orbit. Then lower **Settings → Appearance →
Window opacity**. A **Copy Niri transparency rule** button is available on that
page when a Niri session is detected. The same rule ships in
`assets/niri-window-rule.kdl`. It affects Orbit only and does not lower text
opacity or disable your other window rules. To undo it, remove that block.
If your window has another application ID, inspect it with `niri msg windows`
and adjust the match; the current native Wayland build uses the ID shown above.

This follows Niri's documented border behavior; the compositor itself has not
been run in this build environment:
https://github.com/niri-wm/niri/wiki/FAQ
https://github.com/niri-wm/niri/wiki/Configuration:-Window-Rules

The AppImage no longer sends newer host Fontconfig rules to the bundled older
Fontconfig parser. It uses a compatible bundled policy and still discovers
installed system/user fonts and the included Orbit fonts. It does not modify
`/etc/fonts` or silence warning output. Host-specific alias/rendering policies
are not imported into this portable configuration. Existing FONTCONFIG_FILE or
FONTCONFIG_PATH environment overrides are honored; if you set these yourself,
they can still select an incompatible policy. Source installations continue to
use your distro's Fontconfig library and configuration as a pair.

For remaining issues, capture:

```bash
./Orbit-Explorer-0.6.6-x86_64.AppImage --diagnostics
```

The diagnostic prints and closes the window. The portal registration warning
is separate and may still depend on your host session; Orbit does not replace,
reconfigure or disable portal services.

## Linux — AppImage

Download the AppImage, then run from its download directory:

```bash
chmod +x Orbit-Explorer-0.6.6-x86_64.AppImage
./Orbit-Explorer-0.6.6-x86_64.AppImage
```

If FUSE mounting is unavailable, the AppImage runtime offers:

```bash
./Orbit-Explorer-0.6.6-x86_64.AppImage --appimage-extract-and-run
```

Keep the AppImage wherever you normally keep applications. It reuses
`~/.config/orbit-explorer/settings.json`, including existing pins and themes.
For an AppImage update, close Orbit and replace the old AppImage with the new
one. The source-tree `update.sh` is not an AppImage updater.

Computer-wide filename search still uses your **existing plocate index**;
mounting uses **udisks2**, and the Linux audio patchbay uses **PipeWire** tools.
These services remain host dependencies, not replacement services bundled by
Orbit. For CachyOS/Arch:

```bash
sudo pacman -S --needed plocate udisks2 glib2 pipewire
sudo updatedb
```

Use the equivalents from your distribution on other Linux systems. Without
plocate, visible files remain searchable and browsing/editing still work.
Protected mounts may require your existing desktop authorization agent.

## Linux — Flatpak

Install Flatpak and Python 3 using your distribution's package manager. Extract
the source ZIP, open a terminal in `Orbit-Explorer`, and build from the downloaded
AppImage (which must be executable):

```bash
bash packaging/flatpak-from-appimage.sh "$HOME/Downloads/Orbit-Explorer-0.6.6-x86_64.AppImage"
```

The script prints the output path. Open a terminal in that output directory, then:

```bash
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user ./Orbit-Explorer-0.6.6-x86_64.flatpak
flatpak run io.github.orbitexplorer.Orbit
```

The installer can download the Freedesktop runtime from Flathub. A later local
bundle can be installed over the same application with `flatpak install --user
./NEW-BUNDLE.flatpak`. Keep only one Orbit instance open while changing builds.

**Permissions:** this file manager requests broad host-filesystem access and
host-command execution. Those are needed for the requested file operations,
shell bar, system index, mounts and PipeWire controls. It is not a sandbox for
running untrusted shell commands. It shares Orbit's normal settings file.
The host's `/usr` and `/etc` are exposed under `/run/host`; Flatpak's own system
directories are distinct. Host search results for these locations are mapped
to their exposed paths. Some protected/system locations remain restricted.

## Existing `/orbit-explorer` source installation

Close Orbit and apply the source ZIP in place:

```bash
bash /orbit-explorer/update.sh "$HOME/Downloads/Orbit-Explorer-0.6.6.zip"
```

For a source install, install QtPdf or Poppler alongside the existing packages:

```bash
sudo pacman -S --needed python pyside6 python-numpy qt6-multimedia qt6-svg qt6-webengine poppler ffmpeg ripgrep
```

The PDF fallback uses `pdfinfo`/`pdftoppm` from Poppler. On Debian/Ubuntu or
Fedora the corresponding command-line package is `poppler-utils`.

## macOS — create DMG and PKG on a Mac

This step needs a Mac running Sequoia/Tahoe, Apple's command-line developer
tools and a native Python environment. Build separately on Apple Silicon and
Intel for separate architecture-specific artifacts; the script does not claim
to create a universal binary.

1. Install Apple's command-line tools with `xcode-select --install`.
2. If using Homebrew, install `python@3.12`, `ffmpeg` and `ripgrep`.
3. Extract the source ZIP and open Terminal in `Orbit-Explorer`.
4. Run:

```bash
python3.12 -m venv .venv-build
source .venv-build/bin/activate
python -m pip install PySide6==6.11.2 numpy pyinstaller==6.16.0
bash packaging/build-macos.sh
```

The output is in `build-macos/`:

- `Orbit-Explorer-0.6.6-arm64.dmg` and `.pkg` on Apple Silicon;
- `Orbit-Explorer-0.6.6-x86_64.dmg` and `.pkg` on Intel.

**DMG installation:** open the generated DMG and drag Orbit to Applications.
**PKG installation:** open the generated PKG and follow Installer's prompts;
it installs `Orbit.app` into `/Applications`. Use one method, not both.

Local builds are unsigned/ad-hoc unless you supply your own Developer ID
identities in `ORBIT_MAC_APP_IDENTITY` and `ORBIT_MAC_INSTALLER_IDENTITY`.
Public distribution additionally needs Apple notarization/stapling through
your own developer account; that has not been performed here. Do not disable
Gatekeeper system-wide. For a trusted local build, follow macOS's normal
per-app Open/Privacy & Security approval flow if it prompts.

macOS filename lookup uses Spotlight (`mdfind`); drive operations use
`diskutil`; Trash uses Finder and `.Trash`/per-volume `.Trashes`. Grant only
the Files & Folders/Finder Automation access you need. Disk Utility remains
the place to unlock encrypted volumes. The PipeWire patchbay and live
Caelestia palette are Linux-specific and are not recreated with a competing
index or audio server on macOS. Validate the port on a Mac before relying on
it for important file operations.

## Rebuilding Linux packages

Use Linux x86-64, Python 3.12, PySide6 6.11.2, NumPy, PyInstaller 6.16.0,
FFmpeg/FFprobe, ripgrep, appimagetool, Flatpak, and Qt's platform-library
dependencies (including `libxcb-cursor0` on Ubuntu). Then run:

```bash
bash packaging/build-linux.sh
```

Use a new build directory if staging already exists. The build specification
is shared by the two Linux package formats. Source, build scripts and
third-party notices are included so the packages can be inspected/rebuilt.
