# Orbit Explorer 0.6.6

A native Qt file explorer for CachyOS, Hyprland, and other Linux desktops.
Orbit presents folders and files as a rotatable, connected node globe. Every
line is a parent/child filesystem relationship. File nodes use logarithmic size
scaling; folder nodes use an estimate of their immediate contents. The local
neighborhood is bounded to 680 nodes by default.

## Changed in 0.6.6

Panel animations now match Orbit's original cubic ease-out and fade style,
without bounce or overshoot. Search/info bars, Spotlight, audio and dialogs
fade in place. File panels and video editing tools use live layout slides with
the same easing, keeping native video surfaces live. Opening and closing remain
reversible, and existing duration, fade, travel and per-area toggles are retained.
The bounce control is removed; legacy bounce values are ignored.

Settings → Panel animations includes a frame-rate target (60, 120, 144 or
240 FPS; default 120). Precise, monotonic-time pacing drops late frames rather
than queueing catch-up work. Repeated pixel sizes skip layout work, dense node
clouds retain their sharp cache during file-panel slides, and opacity effects
are disabled once fades finish. Actual displayed FPS depends on display refresh,
the compositor and workload; no Hyprland, Niri or macOS performance guarantee
is implied. Fresh settings use the original sidebar's 240 ms duration; existing
custom durations remain unchanged.

## Added in 0.6.5 (superseded motion style)

The panel motion polish now animates bars and panels in both directions.
Closing the selected/search sidebar, Spotlight, command bar, file panels,
audio dock, video editing tools and dialogs uses a bounce-out transition.
Reopening during the exit reverses it cleanly, and closing a file panel waits
until its exit completes before removing the editor. The animation master
switch and duration, bounce, travel, fade and per-area settings apply to both
entrances and exits.

## Added in 0.6.4 (superseded motion style)

A small polish update on the corrected 0.6.3 source:

- New file/player panels and the selected/search sidebar expand smoothly with
  a small bounce. Video editing tools also animate when revealed. Dialog
  content enters smoothly, including audio routing, without repositioning
  native desktop windows.
- **Settings → Panel animations** has a master switch, separate file/sidebar/
  dialog switches, duration (100–1200 ms), bounce strength, travel amount and
  optional sidebar fade. Bounce 0 gives smooth motion without overshoot;
  disabling the master switch opens instantly. Settings persist across restarts.
- Interacting with a panel or its divider ends its entrance immediately. Node
  clouds reuse their sharp rendering cache during expansion, then repaint at
  the final size. Layout sizes are saved after motion settles.
- Top pinned badges show a theme-colored hover outline and pointing cursor,
  a pressed state and a selected/current-folder state. Drop-hover blinking
  remains available. Pin feedback remains live while panels animate.
- Audio routing has a visible **Close** button. Closing stops its polling;
  reopening resumes the current session.

## Added in 0.6.3

This source bundle starts from the attached 0.6.2 release and combines both
attached input patches. The later patch includes the earlier input changes.
All existing 0.6.2 features, assets and packaging recipes are retained.

- Settings → Controls adds rotation choices for trackpads: Middle-button,
  Alt/Option + left-drag, empty-canvas left-drag, or right-button drag. Optional
  two-finger scrolling rotates; Ctrl/Command + scroll zooms. Existing axis
  inversion settings still apply.
- Folder double-click uses Qt's native event and a repeated-click fallback.
  Return/keypad Enter opens selected items when the graph or selected-items
  panel has focus, while text inputs keep their existing behavior.
- Videos open with playback controls first. **Edit video** reveals the timeline,
  trimming and export controls; **Done editing** hides them while preserving
  playback position, clips and undo history.

The ZIP contains source, not rebuilt AppImage/Flatpak/DMG/PKG binaries. Use the
existing in-place updater with `Orbit-Explorer-0.6.3.zip`. No separate patch
installation is needed.

## Fixed and added in 0.6.2

- Connections use their destination node's configured **Folders** / **Files**
  color. Selecting nodes keeps their incoming connections bright and turns
  other connections gray. Multiple selection is supported; clearing it restores
  the normal colors. Selection takes priority over search dimming.
- Settings changes update only affected components. Checkbox toggles no longer
  reapply the entire stylesheet, clear icon caches, rebuild pins or restart
  search. Visual work is coalesced to a 16 ms timer; saves wait for a 250 ms pause
  and flush when settings/the app closes.
- Opacity uses individually painted translucent surfaces, without a stylesheet
  rebuild or node redraw for every slider tick. Splitter dragging translates a
  sharp cached cloud instead of resampling a high-DPI texture on every move.
- Flight controls clearly show **minimum 150 ms** (range 150–6000 ms). Turn off
  **Animate search navigation** for a direct jump once the destination loads.
- Niri settings includes a **Copy Niri transparency rule** button. See INSTALL.md:
  Niri's solid border/focus-ring background can hide the desktop behind an
  otherwise translucent Orbit window. No compositor config is edited by Orbit.
- Linux portable builds pair bundled Fontconfig with a compatible policy instead
  of parsing newer host conf.d rules. System/user fonts remain available, but
  host alias/rendering-rule customizations are not imported. Explicit
  FONTCONFIG_FILE/PATH choices are respected. Host commands retain host defaults.
- `--diagnostics` prints the Qt platform, scale, alpha-buffer information,
  opacity, Niri detection and whether the bundled font policy is active.

Controlled offscreen A/B measurements (680 nodes, 2× scale, 20 changes per case):
median opacity updates 246.89 → 9.55 ms; inversion-checkbox updates
226.93 → 0.03 ms; live splitter updates 8.44 → 6.26 ms. This includes event
processing/painting in this environment, not a claim about Niri/GPU frame rates.

The 0.6.2 suite completed in isolated groups: **117 tests**, 116 passed and one
skipped because Linux `/proc` is unavailable here. Frozen startup/diagnostics
checks passed with an 8-bit alpha surface and the bundled font policy active.
The source updater is checked from 0.6.1 to 0.6.2, including repeat no-op,
preserved preferences/unrelated files, upgraded startup, and rollback.

## Fixed and added in 0.6.1

- Fixed the reported `TypeError: 'Orbit' object is not callable`: the header
  no longer hides Qt's `window()` method, and the application event filter uses
  Qt's base method when identifying a widget's window.
- The graph and node caches render at the window's actual pixel density,
  including fractional scaling, and rebuild when changing displays/scales.
  High-DPI raster caches have byte limits. Image/video previews use up to 512px.
- Removed the opaque viewport backing layer. The opacity slider now controls
  real background alpha while keeping node artwork and text readable.
- Prefer native Wayland when available; respect an explicit QT_QPA_PLATFORM.
- **Exact** toggles strict search in the top bar and Spotlight (also in Settings
  → Controls). It matches the entire filename, including extension and case.
  `Report.txt` matches only `Report.txt`, not `report.txt` or `Report.txt.bak`.
  Filters still combine; `contains:` stays a literal phrase search but becomes
  case-sensitive. Normal search keeps its case-insensitive substring behavior.
- Sweet Rainbow folders and Candy file/device SVGs are bundled with their GPL
  licenses, and selected by default for new settings. Existing icon choices and
  per-type overrides are preserved. Choose **Sweet (bundled)** under Settings
  → Icons & previews to switch an existing installation.
- Desktop identity now matches the packaged desktop file. A separate Qt/portal
  registration warning can still depend on the host session; it is not the
  Python event-filter exception above. No portal services are replaced/disabled.

Niri-specific compositor/portal behavior still requires testing on the target
desktop. Local regression tests exercise the reported key-event path, real
background alpha, 1.5×/2× rendering, strict queries, and bundled icons without
an installed theme.
The complete 0.6.1 suite was run in three isolated groups: 110 tests,
109 passed and one skipped because this environment does not expose Linux
`/proc`. No failures. The updater is additionally checked from 0.6.0 to 0.6.1,
including repeat no-op, preserved preferences, startup, and rollback.

## New in 0.6.0

- Native video timeline: trim by dragging clip edges or entering source in/out,
  split at the playhead, remove clips, add files, drag to rearrange or leave gaps,
  stitch gaps closed, undo, preview, save/open timeline projects, and export.
  It is a simple single-track editor; gaps become black video and silence.
- Full-resolution image crop, 90-degree rotation, freehand drawing, pen color
  and width, undo, resize/quality controls, encoded-size estimates, and export
  to installed Qt image formats. Originals remain unchanged.
- Right-click **Convert to…** offers compatible image/audio/video, ZIP/TAR,
  and TXT/Markdown/HTML output formats. Available media encoders are detected.
- Left-drag moves files on release. Right-drag a node for an action chooser;
  Settings lets you choose the centered dialog or a cursor-adjacent menu.
- **Empty Trash…** and confirmed permanent deletion of selected Trash items.
- Saved main-window size, pane proportions, viewport split tree/cameras, and
  open file-panel layout. Compositor rules/minimum sizes can constrain restore.
- One continuous configurable search flight, with duration, easing, rotation
  and crossfade settings; disabling it loads only the destination directly.
- Lost-resize/mouse state is cleared on window deactivation and caches are
  rebuilt on return, addressing the stale-snapshot workspace symptom.
- Ctrl+Q closes the active viewport, or the application when only one remains.
- PDF builds include QtPdf; source installations can fall back to Poppler.
- Right-click archives for **Extract to Home**, **Extract here**, or **Extract
  to…**; right-click any selected regular files/folders for **Compress to ZIP…**.
- Hold Tab to fade names in **below their existing nodes**, without changing
  the camera, arrangement, node size, or view. Release it to fade names out.

See **[INSTALL.md](INSTALL.md)** for AppImage, Flatpak, source-update and macOS
build/install steps, compatibility requirements, permissions and known limits.
The macOS adapters/build script are provided, but require validation on a Mac.

## Added and fixed in 0.5.0

- Right-click a drive and choose **Rename in Orbit…**. Saved display names use
  hardware identifiers where available; this does not relabel or format disks.
- Drag the dividers between the sidebar, cloud, details, header/navigation,
  command area, sidebar sections, path/search inputs, and open file panels.
  Sizes change while the mouse is held. Main layout proportions persist.
- Native video playback, image/GIF viewing, a text/code editor, PDF viewing,
  and ZIP/TAR browsing and extraction. Each open panel has a dotted line to
  its source node. Multiple documents can stay open in resizable tiles.
- Audio play, mute and close controls use vector icons with stable sizing.
- Clicking the black hole opens local Trash **inside Orbit**, honoring
  `XDG_DATA_HOME`; right-click offers detected Trash folders on mounted drives.

## Fixed in 0.4.1

- Dropdowns and context menus have explicitly painted opaque backgrounds,
  independent of main-window translucency and external Qt theme styling.
- Path completion is suggestion-only: muted ghost text never edits your input.
  Enter confirms a suggestion; a second Enter opens the confirmed path.
- Default pins follow preset and live Caelestia colors. Explicit custom pin
  colors are retained; right-click a pin and choose **Use theme color** to reset it.

## Added in 0.4.0

- Live, relevance-ranked path completion for folders and files.
- An explicit **Move here / Copy here / Link here / Cancel** chooser on drop.
- Rounded navigation, panels, selection cards, and a reorganized settings window.
- Bundled Manrope, Nunito Sans, and Inter fonts, plus an installed-font dropdown
  and adjustable interface text size.
- Image/video previews and folder thumbnails beside selected-item information.

## First installation

Extract the archive and open a terminal in `Orbit-Explorer/`:

```bash
sudo pacman -S --needed python pyside6 python-numpy qt6-multimedia qt6-svg qt6-webengine \
  plocate ripgrep udisks2 glib2 ffmpeg pipewire
sudo updatedb
./run.sh
```

Install the launcher with `./install-desktop.sh` and keep the project directory
in place. Existing settings are upgraded automatically with defaults for new
options.

The app needs PySide6 with Qt 6.8 or later for internal audio. Native video
uses Qt Multimedia; PDF viewing uses QtPdf/QtPdfWidgets, supplied by
[`qt6-webengine` on Arch/CachyOS](https://archlinux.org/packages/extra/x86_64/qt6-webengine/files/).
Video thumbnails use `ffmpeg`; content searches use `ripgrep`. The audio patchbay uses the
`pw-dump` and `pw-link` tools from the existing PipeWire session.

## Automatic installer for updates

**Already installed in `/orbit-explorer`?** Close every Orbit window. Extract
this ZIP somewhere else (for example Downloads), open a terminal in its
`Orbit-Explorer/` folder, and run:

```bash
./update.sh --target /orbit-explorer
```

The updater installs this extracted release into the existing folder. It does
not create `/orbit-explorer/Orbit-Explorer/`. Your existing launcher keeps
pointing to the same installation. Updates from the earlier 0.2 and 0.3 builds
are supported. If an extractor dropped executable permissions, use
`bash update.sh --target /orbit-explorer`.

**For subsequent releases**, download the new ZIP and install it directly,
without extracting it:

```bash
/orbit-explorer/update.sh "$HOME/Downloads/Orbit-Explorer-0.6.6.zip"
```

Replace the example filename with the actual download. For another install
location, pass `--target /your/install/path`. When installing an extracted
release, omitting `--target` defaults to `/orbit-explorer`; when installing a
ZIP, it defaults to the folder containing the updater you launched.

The updater automatically:

- Validates the release manifest, file hashes, and ZIP paths before updating.
- Refuses to update a running installation and blocks startup during updates.
- Backs up the previous application files, replaces them in place, and removes
  obsolete files owned by an earlier release.
- Preserves unrelated files and settings, including pins, themes, volume,
  recent folders, and keybindings in `~/.config/orbit-explorer/settings.json`
  (or your custom `XDG_CONFIG_HOME`).
- Restores the old application if installation fails. Running the same update
  again makes no changes when its files are already installed.

Backup paths are printed on completion and retained in
`/orbit-explorer/.orbit-backups/`. To undo the most recent update, close Orbit
and use the exact backup path printed by that update:

```bash
/orbit-explorer/update.sh --rollback /orbit-explorer/.orbit-backups/BACKUP-NAME
```

After a power loss or forced termination, run this before restarting:

```bash
/orbit-explorer/update.sh --recover
```

If the installed updater was itself interrupted during its first installation,
run `./update.sh --target /orbit-explorer --recover` from the extracted release.
Recovery is also attempted automatically before the next update. Backups are
kept until you remove them; application files you customized can be recovered
from their `files/` subfolder.

The updater needs Python 3 and write permission to the installation. If the
installation is owned by root, run **only the update command** with `sudo`;
start Orbit normally as your own user afterward. It does not change system
packages: install any newly required dependencies using the command above.

There is no hosted release feed yet, so this automates installation from a
downloaded release; it does not check the internet or download future builds.
Install ZIPs from a trusted source. Manifest checks detect corruption; they
are not a publisher signature. Old ZIPs without a release manifest cannot be
used as an update source; use the rollback backup for an earlier version.

## Views, selection and files

| Input | Action |
| --- | --- |
| Middle-drag | Orbit the globe. Both directions can be inverted in Settings. |
| Right-drag | Truck/pan the view. |
| Wheel | Zoom. |
| Fit (viewport header) | Fit that cloud into its viewport. |
| Click / Ctrl+click | Select one node / toggle nodes in a multiple selection. |
| Shift+drag | Rectangle-select nodes. Shift+click twice also defines a rectangle. |
| Hold Tab | Fade names in below unchanged nodes; release to hide them. |
| Ctrl+T | Split the active viewport and open Home in the new tile. |
| Ctrl+D | Duplicate the active folder, camera, and selection into a new tile. |
| Ctrl+W / tile × | Close the active tile, retaining at least one viewport. |
| Ctrl+Q | Close the active tile; close Orbit if it is the last tile. |
| Double-click | Enter a folder, open a file, or open/mount a partition. |
| Right-click | File-, folder-, or partition-specific context menu. |

Tab is intercepted before focus traversal while a viewport has focus, and
keyboard auto-repeat no longer releases/restarts labels. The held key is
customizable. Dense clouds can have overlapping labels; no nodes are moved to
make room. Pan or zoom normally if needed. Text inputs retain their normal keyboard behavior.

The active tile has a teal border. Each tile keeps its own location, camera,
selection, and back/forward history. Tile dividers are resizable; further splits
choose the longest dimension. Address navigation, commands, and selection
information follow the active tile.

Selected-file details appear beneath each name in compact tree branches:
size, file type, modified date, and immediate item count for folders. Folder
sizes here are explicitly labeled **direct files**, not recursive totals.
Properties can calculate the recursive apparent size on demand.
Each selected item also shows a preview: image/video content, a custom pinned
folder thumbnail, or its configured file-type/folder icon. These reuse the
Orbit preview cache and load asynchronously; selecting many files does not
synchronously decode their previews.

## Live path completion

Press **Ctrl+L** or click the address bar and start typing. Suggestions update
live from the parent folder: `/home/user/p` can suggest `/home/user/Pictures/`.
Matching is case-insensitive; exact matches rank first, then prefixes, then
substrings. Folders precede files at the same match level; pins and recent
folders receive priority among otherwise equivalent matches. Full paths and
icons help distinguish suggestions.

Suggestions appear in muted text, with a gray inline suffix when possible.
Typing, hovering, and Up/Down never rewrite the path you entered. Clicking a
suggestion only stages it. **Enter** explicitly fills in that suggestion without
navigating, so you can continue typing a deeper path; a second **Enter** opens
the confirmed path. **Tab** changes focus without accepting a suggestion.
**Escape** dismisses suggestions. A trailing slash does not suggest the first
child automatically; type the next component to see matches.
Absolute paths, `~/` paths, and paths relative to the active viewport work.
Hidden names appear when you type a leading dot, or enable Show hidden files.

Completion uses Qt's asynchronous `QFileSystemModel` for the immediate parent
directory. It does not recursively scan your computer or create an index.
Computer-wide search still uses the existing plocate index.

## Native drag and drop

Drag selected nodes onto pinned places, a directory node, or another tile's
empty canvas. The selection gathers into an animated cluster beside the
pointer. A **left-button drag moves on release** without a prompt. A
**right-button drag on a file node** opens **Move here / Copy here / Link here /
Cancel**. Configure that chooser as a centered dialog or a menu beside the
cursor. Right-dragging empty canvas still pans. Link creates symbolic links;
Cancel or closing the chooser leaves files untouched. Existing destination
names are refused, and dropping an item back into its own folder is a no-op.

Drags export standard local `text/uri-list` file URLs through Qt's native drag
system, so upload targets such as Discord can accept them. External uploads
request a copy and Orbit does not delete the originals. Files dragged into
Orbit from another app use the same left/right-button behavior. Orbit acknowledges the
native drop as a copy/receipt before the chooser opens, so another application
cannot delete its source files if you cancel. Sources that insist on a
move-only drag are not accepted.

Hover over a directory during a drag to spring-open it. The whole warning lasts
**1.5 seconds**: a 600 ms dwell, then three 300 ms blinks. It opens as the third
blink finishes. Leaving, dropping, or canceling at any phase resets the warning;
you can immediately retry the same folder or a different folder. The pending
files remain attached to the drag while the destination graph loads.

File transfers run outside the GUI thread, refuse existing destination names,
and refresh all views on completion. Moves use the system's `mv` with exact
no-clobber destinations. Context menus also offer Send to, Properties, Rename,
Copy/Cut/Paste, New folder/file, and Move to trash where appropriate.

## Black hole Trash

Faint, slowly warping light marks the **bottom-right of the viewport area**.
Hover there to reveal a dark core, a glowing accretion ring, and the Trash
label. Leaving fades the black hole away while its light distortion remains.
It follows your current theme, including the live Caelestia palette.

Drop one or several files onto the black hole to move them to the system
Trash. A confirmation appears before the operation, and the inward spiral
plays after it succeeds. Canceling keeps the original files. This uses the
existing `gio trash` backend; files are not permanently deleted. Drives,
mounted roots, and the folders currently open in your viewports are excluded.

Click the black hole to open `$XDG_DATA_HOME/Trash/files` inside Orbit, falling
back to `~/.local/share/Trash/files` when that variable is unset or relative.
Right-click the black hole to choose an existing per-user Trash on a mounted
drive. This is a file view of the Trash, not a browser URL or an aggregate
virtual directory. Original-path restoration from `.trashinfo` is not yet
implemented; a desktop Trash manager remains useful for **Restore**.
Choose **Empty Trash…** from the black hole's right-click menu to permanently
remove contents of Home Trash and detected mounted-drive Trash. Deleting
selected items already inside Trash also means permanent deletion. Both actions
require confirmation; they cannot be undone and never re-trash the items.
The target stays at the workspace corner when splitting
views or opening the selection panel. Animation repaints only the small
target, reuses a cached glow, and pauses while hidden or minimized.

## Live search

Type while a viewport has focus, or press Ctrl+F, to open Spotlight. Matching
nodes stay bright; other nodes are dimmed. Selecting a result flies through its
directory path. Disable Spotlight in Settings to use the inline search field.
The Navigation settings page controls the total flight duration (lower is
faster), easing, orbit rotation and crossfade amount. Scenes are prepared in a
worker, then played as one animation without per-directory pauses. Turning
animation off skips intermediate directories and loads the destination directly.

| Query | Meaning |
| --- | --- |
| `holiday` | Case-insensitive filename substring. |
| `is: png` | Files with the PNG extension. |
| `is: jpg,jpeg,png` | Any of those extensions. |
| `date: 28/09/2026` | Modified on that date, in the system's local timezone. |
| `contains: I remember when` | Literal, case-insensitive text inside documents. |
| `notes is: md date: 28/09/2026 contains: "I remember when"` | Combine filename, extension, date, and contents filters. |

`is:` means **file type/extension**. Unprefixed text searches the filename.
Quotes protect a content phrase that itself includes strings such as `is:`.
Incomplete or invalid filters show a hint while you type.

Computer-wide candidate paths come from **plocate's existing index**. Orbit
also includes files already loaded into its viewports. `contains:` passes those
candidates to **ripgrep**; it does not make a content index or recursively walk
the computer. Binary files are excluded by ripgrep. PDF/Office extraction is
not included; this is for text files such as TXT, Markdown, logs, and source
code. Each new query cancels the previous search and its child process.

Index coverage follows `/etc/updatedb.conf` and access permissions. Newly
created files outside visible folders or newly mounted volumes may need an
index update. Check the system schedule with
`systemctl status plocate-updatedb.timer`.

## Sidebar and shell commands

The sidebar lists physical drives; opening one shows its partitions and
filesystems as nodes. Mount, unmount, and unlock go through `udisksctl` and the
existing desktop authorization policy. An authentication agent may be needed
in Hyprland for protected volumes. The running system root cannot be unmounted.
Recent folders appear below drives and are retained across launches.
Right-click a physical drive in the sidebar or its root node to rename its
Orbit display name. **Use hardware name** resets it. Aliases prefer WWN,
serial, or UUID, with the device path as a fallback for unidentified devices.
No disk permissions or filesystem labels change.

Use the **>_** button or **Ctrl+`** to open the command bar. Enter runs the
command in your configured shell with its working directory set to the active
viewport's folder. Output is streamed into the panel; Stop terminates the
command's process group. Up/Down recalls commands from the current session.

Each command starts in the current folder afresh. The bar is for shell commands
and scripts, not full-screen terminal applications. A command such as
`cd subfolder && ls` changes directory for that one command. Running commands
does not block navigating or splitting views.

## Audio player and routing

Opening an audio file in Orbit fades in the bottom-left mini-player and FFT
spectrum panel. Controls include play/pause, clickable seeking, volume from
0–100%, and mute. Volume is saved between launches. A dotted tether connects
the player to its source node, including across tiles.

## Built-in file panels

Double-click a supported file, or choose **Open in Orbit** from its node menu.
Disable **Open supported files inside Orbit** in Settings to use external apps
by default. The panel's external-open button is always available. Audio keeps
its separate setting and floating mini-player.

| Type | Built-in controls |
| --- | --- |
| Video, such as MP4, WebM or MKV | Native preview with mute/volume, timeline trim/split/reorder/gaps/stitch, project save/load and export. |
| Images, such as PNG, JPEG, WebP or SVG | Crop, rotate, freehand ink, undo, resize/quality and format export; up to 64 megapixels for editing. |
| Animated GIF | Playback, pause and speed control. |
| Text, Markdown, code, JSON, CSV and configuration files | Plain-text editor, Find, Save, Save as and Ctrl+S. |
| PDF | Native scrollable, multi-page view fitted to panel width. |
| ZIP and TAR, including gzip/bzip2/xz TAR archives | Entry list and **Extract to…**. |

File panels tile below the cloud with live dividers. The locate button flies
back to their file node. Dotted lines follow nodes across viewports; after
navigating away, a small named proxy at the cloud edge retains the connection.
Closing a panel stops its playback. Reopening an already-open file reuses it.
Image/video edits are non-destructive and prompt before being discarded.
Video exports support MP4, MKV, MOV, WebM, AVI, MPEG, OGV and GIF when their
encoders are installed. Conversion additionally supports MP3, FLAC, WAV, OGG,
Opus, M4A, AAC, AIFF and AC3. GIF image conversion exports its first frame;
animated GIF playback remains in the GIF player. This is not a multi-track
compositor, subtitle editor, or lossless packet-cutting tool; video exports
are re-encoded at the selected size/frame rate.

The editor supports UTF-8 and BOM-marked UTF-16, with an 8 MiB input limit.
Saving preserves newline style and permissions, writes atomically, and refuses
to overwrite a file changed externally. Save as creates a new copy. Unsaved
edits prompt before closing. Markdown/HTML are edited as text, not rendered
or executed; office documents and unsupported formats open externally.

Archive extraction runs in a worker and creates a fresh, uniquely named folder
inside your chosen destination. Existing files are never replaced. Traversal
paths, archive links, special files and encrypted ZIPs are rejected. Limits
are 10,000 entries and 4 GiB expanded; the preview lists the first 1,000 entries.
**Extract here** stages/validates before placing top-level entries and refuses
collisions; it does not overwrite or merge existing folders. **Extract to Home**
creates a new extraction folder in your home, and **Extract to…** creates one
in your chosen directory. Compression preserves selected folder structure and
empty directories; symbolic links and special files are refused. Archive
conversion supports ZIP, TAR, TAR.GZ, TAR.BZ2 and TAR.XZ. RAR, 7z and encrypted
archives require an external archive manager.

## Audio routing

The **Audio routing** button opens a live PipeWire patchbay:

- Devices and applications appear as movable node cards with input/output
  sockets and current links.
- Drag an output socket to an input socket to connect them.
- Right-click a cable to disconnect it, or select it and press Delete.
- Wheel zooms, dragging empty space pans, and Fit view frames the graph.
- The display refreshes while open and preserves card positions. Changes act
  on the existing PipeWire session through `pw-link`.

Inactive cards with no exposed ports are listed but cannot be connected until
the session exposes ports. Session policy can recreate managed links. Orbit
does not replace PipeWire/WirePlumber or implement a saved routing profile.

## Appearance and performance

The gear opens colors, presets, transparency, installed fonts, thumbnails,
file-type icons, orbit inversion, the held-name key, node spacing, audio, and
Spotlight behavior. Presets include Midnight Teal, Black & Deep Red,
Purple & Dark Gray, and System (Caelestia). The Caelestia palette reads
`~/.local/state/caelestia/scheme.json` by default, with a path override available.
Installed Sweet/Candy themes and per-type icon/image overrides are supported.
Pinned places use the active palette by default, including live Caelestia
changes. Choose **Color…** on a pin to give it an independent color, or **Use
theme color** to resume palette tracking. Cropped thumbnail artwork is preserved
without tinting. Older pins whose saved color matched a default palette primary
are migrated to theme tracking; other custom colors are retained.

The refreshed interface uses rounded panels, pill-shaped navigation, compact
vector controls, and quieter borders while preserving your existing colors
and transparency. Settings now has separate Appearance, Typography, Controls,
and Icons & previews sections. In Typography, choose a bundled quick style or
use the searchable font-family dropdown for any installed font. A live preview
and 9–16 pt interface size control help compare them. Manrope is the default
for new settings; your saved font is retained on update. The bundled fonts are
loaded privately by Orbit, not installed system-wide, and their OFL licenses
are included under `assets/fonts/`.

The default cloud has longer links and wider child clusters. The spacing
slider adjusts every viewport without re-reading the directories. Two small
moons orbit the center node; their animation can be disabled.

Rendering caches image/icon previews, scaled sprites, complete bordered node
artwork, projection state, and the static graph layer. Thumbnail loading,
search, metadata, transfers, and directory scans happen outside GUI painting.
Preview updates are coalesced. Satellite animation reuses the cached graph.
While a divider is held, the cloud scales its cached frame to its live bounds
instead of reprojecting hundreds of nodes for each pointer movement. Releasing
the divider redraws at the final size. Media and document widgets remain live.

Settings live in `~/.config/orbit-explorer/settings.json`. Hyprland hides
redundant window buttons; other desktop sessions show them. The window uses
Wayland's system-move request and compositor-managed transparency/blur.

## Validation

From `Orbit-Explorer/`:

```bash
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

The suite covers live path completion and ranking, completion keyboard input,
stale-query handling, explicit drop choices, symbolic links and collisions,
font selection, selected-item previews, the Trash target's hover and file drops,
cancel/failure handling, local and mounted Trash resolution,
layout anchoring and animation lifecycle, plus in-place
updates, rollback and interrupted-update recovery,
settings preservation, archive validation, installation locking, native
file-URL payloads and Qt drop events, cross-tile moves,
external copies, repeated held keys, timed hover cancellation/retry, search
filters with actual ripgrep matching, indexed candidate processing, metadata,
command working directories, volume/mute icons, persistent drive aliases,
live divider geometry before release, cached graph resizing, simultaneous
image/PDF/archive panels and source tethers, real video/GIF decoding,
text saving/conflicts/unsaved-close handling, ZIP/TAR extraction and path/link
rejection, drive grouping, and PipeWire graph
parsing/command adapters. PipeWire process tests use fixtures, not real hardware.

In a synthetic 680-node offscreen orbit benchmark at 1100×750, the tested 0.2
build took about 123 ms per redraw and 0.3 about 13.8 ms (median, warmed caches,
including all parent/child connections).
This is a controlled rendering comparison, not a hardware-independent FPS
promise. Actual Discord acceptance, Hyprland compositor behavior, audio-device
routing, and mount authentication still need validation on the target desktop.

For 0.6.0, the suite additionally checks real multi-format timeline exports,
trim lengths, black gap pixels, sound conversion, image edits/exports,
ZIP round-trips, permanent Trash safety, saved layouts, stationary held labels,
continuous/disabled navigation and an actual Poppler fallback render.
The 0.6.0 local run had 100 tests, 99 passed and one skipped because this environment
does not expose `/proc/self/exe`. The frozen Linux application passed startup
and native QtPdf/video import checks; all 509 AppImage payload files matched
the staged build. Flatpak export and macOS installers are not verified releases;
see INSTALL.md for the build limitations and scripts.
The previous separate 680-node offscreen resize benchmark measured 1.24 ms median
and 1.71 ms at the 95th percentile while scaling the cached cloud. This measures
the graph's live resize path, not whole-window or compositor performance.
