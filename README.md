
# Orbit Explorer

Because the traditional file explorers are just a little too boring.

The main reason Orbital Explorer was created was due to traditionally styled - Windows file explorer or Mac finder esque - file explorers feeling unoptimised in their speed and functionality. Orbit's main mission is to expedite the often drudgerous process for heavy file management tasks - such as video and photo editing or general data management. Orbit is a native Qt file explorer for CachyOS, Hyprland, and should work for other Linux desktops, but is tested only on Caelestia on CachyOS. Orbit presents folders and files as a rotatable, connected node globe. 

The main feature is the "Orbit view", which is a pseudo 3D view of all your files in your selected directory, inspired by [Obsidian](https://obsidian.md/) note-taking app.

## AI

As someone who has practically no idea how to code, everything except for the general concept and overall vision was AI generated with GPT-6 Astra. This project was created solely because I wanted an alternative to the default file explorer and I only decided to publish it because my friends wanted it as well, showing a clear demand for this. 

## Why switch?

- It looks pretty sick, one of the main goals was to make this look clean and to tailor to the "Linux ricing" aesthetic.
- The amount of functionality that ships with Orbit - as lightweight as it is - generally just improves quality of life. It's essentially an all in one for most daily use and work.
- It's a breath of fresh air and a break from the generic formula used everywhere else.
- Despite it's extensive feature set, it's still simplistic and easy on the eyes. 

## Features

Some of the quality of life features include:

- Native file conversion - such that 3rd party websites do not need to be used.
- Native audio, video and photo viewer within the app (so seperate apps are not needed).
- Lightweight video trimmer / editor, and simplistic photo editor - for smaller changes that can be done outside software.
- Simple audio rerouter - inspired by [qpwgraph](https://github.com/rncbc/qpwgraph)
- [Rofi](https://github.com/davatorium/rofi)-style / MacOS Spotlight search-style file lookup - just by typing in the viewport.
- Sidebar lists disks and partitions, allowing easy mounting and unmounting.
- Terminal option, allowing for shell commands to be executed in current directory.
- ZIP / Archive extraction features.

Shortcuts:

-       Ctrl + T - Opens a new "3D Viewport" file explorer in Home directory.
-       Ctrl + D - Duplicates current directory into new "3D Viewport" window.
-       Ctrl + Q - Closes current file explorer.
-       Ctrl + Left Click - Allows for multiple file selection.
-       Shift + Left Click - Allows for mass file selection.
-       Ctrl + C - Copies currently selected file(s).
-       Ctrl + V - Pastes currently selected file(s).
-       Ctrl + X - Cuts currently selected file(s).
-       Right Click Drag & Drop - Allows for duplication or cutting to seperate file explorer(s).
-       Tab - View names of all files.




| OS | Notes | Status |
| :--- | :--- | :---: |
| Hyprland (Caelestia)|Tested and works natively| ✅ |
| MacOS Sequoia  | Works with a few bugs | 🟨 |
| Hyprland (Niri) |  Works with custom rule | ✅ |

# Orbit Explorer - installation and build notes

## Package status

Linux release artifacts target **x86-64**. The AppImage contains Python, QtPdf,
Qt Multimedia, image codecs, FFmpeg/FFprobe and ripgrep, so it does not depend
on a separately installed PySide6. It was built on Ubuntu 24.04 and requires a
glibc-based distribution with **glibc 2.39 or newer**. CachyOS/current Arch is
the primary target. This is not an ARM or musl/Alpine package.

**Delivered:** the Linux AppImage and source/update ZIP. The frozen Linux
executable passed an offscreen startup check; all AppImage payload files were
verified. Actual desktop/compositor testing is still needed, including the
Hyprland workspace fix. This workspace cannot mount/run the AppImage wrapper
because its `/proc` environment is unavailable.

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

macOS service adapters and a **native macOS build script** are included. The
macOS port has not been built or tested on a Mac in this workspace. No DMG/PKG
should be considered delivered or validated until that script runs on macOS.
Qt 6.11 supports macOS 13+, covering Sequoia 15 and Tahoe 26:
https://doc.qt.io/qt-6/supported-platforms.html

## Linux - AppImage

Download the AppImage, then run from its download directory:

```bash
chmod +x Orbit-Explorer-0.6.0-x86_64.AppImage
./Orbit-Explorer-0.6.0-x86_64.AppImage
```

If FUSE mounting is unavailable, the AppImage runtime offers:

```bash
./Orbit-Explorer-0.6.0-x86_64.AppImage --appimage-extract-and-run
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

## Linux - Flatpak

Install Flatpak and Python 3 using your distribution's package manager. Extract
the source ZIP, open a terminal in `Orbit-Explorer`, and build from the downloaded
AppImage (which must be executable):

```bash
bash packaging/flatpak-from-appimage.sh "$HOME/Downloads/Orbit-Explorer-0.6.0-x86_64.AppImage"
```

The script prints the output path. Open a terminal in that output directory, then:

```bash
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user ./Orbit-Explorer-0.6.0-x86_64.flatpak
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
bash /orbit-explorer/update.sh "$HOME/Downloads/Orbit-Explorer-0.6.0.zip"
```

For a source install, install QtPdf or Poppler alongside the existing packages:

```bash
sudo pacman -S --needed python pyside6 python-numpy qt6-multimedia qt6-svg qt6-webengine poppler ffmpeg ripgrep
```

The PDF fallback uses `pdfinfo`/`pdftoppm` from Poppler. On Debian/Ubuntu or
Fedora the corresponding command-line package is `poppler-utils`.

## macOS - create DMG and PKG on a Mac

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

- `Orbit-Explorer-0.6.0-arm64.dmg` and `.pkg` on Apple Silicon;
- `Orbit-Explorer-0.6.0-x86_64.dmg` and `.pkg` on Intel.

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
