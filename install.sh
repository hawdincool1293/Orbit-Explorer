#!/usr/bin/env bash
# Orbit Explorer source installer. Compatible with macOS's Bash 3.2.
set -euo pipefail

die() { printf 'Orbit installer: %s\n' "$*" >&2; exit 1; }
usage() {
    printf '%s\n' 'Usage: bash install.sh [--source DIRECTORY] [--update] [--dry-run] [--skip-system-deps]' \
      'Run beside app.py in an extracted Orbit release or Git checkout.' \
      '--source DIRECTORY    Use an existing Orbit folder instead.' \
      '--update              Fast-forward a clean Git checkout, then refresh dependencies.' \
      '--dry-run             Print the plan; make no changes or network requests.' \
      '--skip-system-deps    Use already-installed Python and platform helpers.' \
      'Run as your regular user. Only Linux package installation uses sudo.'
}
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install_script_path="$source_dir/$(basename "${BASH_SOURCE[0]}")"
update=0; dry_run=0; skip_deps=0
while [[ $# -gt 0 ]]; do
    case "$1" in
      --source) [[ $# -ge 2 ]] || die '--source needs a directory'; source_dir="$2"; shift 2 ;;
      --update) update=1; shift ;;
      --dry-run) dry_run=1; shift ;;
      --skip-system-deps) skip_deps=1; shift ;;
      --help|-h) usage; exit 0 ;;
      *) die "Unknown option: $1 (use --help)" ;;
    esac
done
[[ -d "$source_dir" ]] || die "Source directory does not exist: $source_dir"
source_dir="$(cd "$source_dir" && pwd -P)"
for file in app.py core.py desktop_backend.py install_lock.py assets/orbit.svg; do
    [[ -f "$source_dir/$file" ]] || die "Missing $file. Extract the full Orbit ZIP first or clone its repository, then use --source."
done
platform="$(uname -s)"
case "$platform" in Linux|Darwin) ;; *) die "Unsupported OS: $platform" ;; esac
manager=''
if [[ "$platform" == Linux ]]; then
    for candidate in pacman apt-get dnf zypper; do
        if command -v "$candidate" >/dev/null 2>&1; then manager="$candidate"; break; fi
    done
    [[ -n "$manager" || "$skip_deps" == 1 ]] || die 'Supported Linux package managers: pacman, apt-get, dnf, zypper. On other glibc distributions, install dependencies first and use --skip-system-deps. Alpine/musl is not supported by the Qt wheels.'
fi
if [[ "$dry_run" == 1 ]]; then
    printf 'Source: %s\nPlatform: %s\n' "$source_dir" "$platform"
    if [[ "$skip_deps" == 1 ]]; then printf '%s\n' 'Use existing system dependencies.'
    elif [[ "$platform" == Darwin ]]; then printf '%s\n' 'Install Homebrew if missing (its official installer may request Apple Command Line Tools), then Python 3.12, Git, FFmpeg, ripgrep and Poppler.'
    else printf 'Install system helpers and Qt runtime libraries with %s (sudo).\n' "$manager"; fi
    [[ "$update" == 0 ]] || printf '%s\n' 'Require a clean Git checkout and its upstream, then git pull --ff-only under the installation lock.'
    printf '%s\n' 'Create/reuse a per-user Python environment; install PySide6 >=6.8,<6.12 and NumPy >=1.26,<3 from binary wheels.' \
      'Check Qt PDF, SVG, video and audio imports; install the user launcher and command.' \
      'Keep this source folder in place. Preferences and existing search/compositor configuration are preserved.'
    exit 0
fi
[[ "$(id -u)" != 0 ]] || die 'Run as your regular user, without sudo. The script requests sudo only for Linux packages.'
if [[ "$skip_deps" == 0 && "$platform" == Linux ]]; then
    command -v sudo >/dev/null 2>&1 || die 'sudo is required to install Linux system packages.'
    case "$manager" in
      pacman) sudo pacman -S --needed python python-pip git ffmpeg ripgrep plocate udisks2 glib2 pipewire \
          libglvnd libpulse libxkbcommon libxkbcommon-x11 xcb-util-cursor libxcb wayland fontconfig ;;
      apt-get) sudo apt-get update
          sudo apt-get install python3 python3-venv python3-pip git ffmpeg ripgrep plocate udisks2 libglib2.0-bin pipewire-bin \
          libgl1 libegl1 libpulse0 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 \
          libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1 \
          libwayland-client0 libwayland-cursor0 libwayland-egl1 libfontconfig1 libdbus-1-3 ;;
      dnf) if ! command -v ffmpeg >/dev/null 2>&1; then sudo dnf install ffmpeg-free; fi
          sudo dnf install python3 python3-pip git ripgrep plocate udisks2 glib2 pipewire-utils \
          libglvnd-glx libglvnd-egl pulseaudio-libs libxkbcommon libxkbcommon-x11 xcb-util-cursor \
          xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil libxcb wayland-libs fontconfig ;;
      zypper) sudo zypper install python3 python3-pip git ffmpeg ripgrep plocate udisks2 glib2-tools pipewire-tools \
          libGL1 libEGL1 libpulse0 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 \
          libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1 \
          libwayland-client0 libwayland-cursor0 libwayland-egl1 libfontconfig1 ;;
    esac
    if [[ ! -s /var/lib/plocate/plocate.db ]]; then
        printf '%s\n' 'Initializing the system plocate database (this first scan may take a while).'
        sudo updatedb
    fi
fi
python_command=python3
if [[ "$platform" == Darwin ]]; then
    brew_command=''
    if command -v brew >/dev/null 2>&1; then brew_command="$(command -v brew)"
    elif [[ -x /opt/homebrew/bin/brew ]]; then brew_command=/opt/homebrew/bin/brew
    elif [[ -x /usr/local/bin/brew ]]; then brew_command=/usr/local/bin/brew; fi
    if [[ "$skip_deps" == 0 ]]; then
        if [[ -z "$brew_command" ]]; then
            command -v curl >/dev/null 2>&1 || die 'curl is required to bootstrap Homebrew.'
            bootstrap="$(mktemp -d "${TMPDIR:-/tmp}/orbit-homebrew.XXXXXX")"
            trap 'if [[ -n "${bootstrap:-}" && -f "$bootstrap/install.sh" ]]; then rm -f "$bootstrap/install.sh"; rmdir "$bootstrap"; fi' EXIT
            curl --fail --location --proto '=https' --tlsv1.2 \
                https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$bootstrap/install.sh"
            /bin/bash "$bootstrap/install.sh"
            if [[ -x /opt/homebrew/bin/brew ]]; then brew_command=/opt/homebrew/bin/brew
            elif [[ -x /usr/local/bin/brew ]]; then brew_command=/usr/local/bin/brew
            else die 'Homebrew installation did not finish. Complete Apple Command Line Tools/Homebrew setup, then rerun this script.'; fi
        fi
        "$brew_command" install python@3.12 git ffmpeg ripgrep poppler
        python_command="$("$brew_command" --prefix python@3.12)/bin/python3.12"
    fi
    if [[ -n "$brew_command" ]]; then export PATH="$("$brew_command" --prefix)/bin:$PATH"; fi
fi
command -v "$python_command" >/dev/null 2>&1 || die 'Python 3.10 or later is required; install it and rerun.'
export ORBIT_INSTALL_SCRIPT="$install_script_path"
"$python_command" - "$source_dir" "$platform" "$update" <<'PY'
import fcntl,json,os,plistlib,re,shlex,subprocess,sys,tempfile
from pathlib import Path

def fail(message):
    raise SystemExit('Orbit installer: '+message)
def run(*args, **kwargs):
    print('+ '+shlex.join(map(str,args)),flush=True)
    subprocess.run(list(map(str,args)),check=True,**kwargs)
def write(path,data,mode=0o644):
    if path.is_symlink():fail(f'Refusing to replace a symlink: {path}')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix='orbit-install-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data if isinstance(data,bytes) else data.encode())
        os.chmod(temporary,mode);os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)

source=Path(sys.argv[1]).resolve();platform=sys.argv[2];update=sys.argv[3]=='1'
if any(c in str(source) for c in ('\n','\r')):fail('Source paths containing line breaks are unsupported by desktop launchers.')
if sys.version_info<(3,10):fail('Python 3.10 or later is required for Orbit and its Qt wheels.')
for helper in (['ffmpeg','ffprobe','rg','plocate','udisksctl','gio'] if platform=='Linux' else ['ffmpeg','ffprobe','rg']):
    import shutil
    if not shutil.which(helper):fail(f'Missing helper: {helper}. Install platform dependencies or rerun without --skip-system-deps.')
home=Path.home()
try:version=json.loads((source/'orbit-release.json').read_text()).get('version','0.0.0')
except (OSError,ValueError):version='0.0.0'
if not isinstance(version,str) or not re.fullmatch(r'\d+\.\d+\.\d+',version):version='0.0.0'
state=(home/'Library/Application Support/Orbit Explorer' if platform=='Darwin' else Path(os.environ.get('XDG_DATA_HOME',str(home/'.local/share')))/'orbit-explorer')
state.mkdir(parents=True,exist_ok=True)
runtime_lock=os.open(state/'installer.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
try:fcntl.flock(runtime_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:fail('Another Orbit installer is running.')
sys.path.insert(0,str(source))
from install_lock import lock_installation
try:source_lock=lock_installation(source)
except (OSError,RuntimeError) as error:fail(str(error))
if update:
    top=subprocess.check_output(['git','-C',str(source),'rev-parse','--show-toplevel'],text=True).strip()
    if Path(top).resolve()!=source:fail('--update requires the Orbit source at the root of its Git checkout.')
    dirty=subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no'],text=True)
    if dirty:fail('Git checkout has local changes. Commit/stash them before --update; nothing will be discarded.')
    run('git','-C',source,'pull','--ff-only')
venv=state/'venv';python=venv/'bin/python'
if not (venv/'pyvenv.cfg').exists():
    if venv.exists():fail(f'Unrecognized runtime directory: {venv}. Move it aside before installing.')
    run(sys.executable,'-m','venv',venv)
if not python.exists():fail(f'Python environment is incomplete: {venv}. Move it aside and rerun.')
run(python,'-m','pip','install','--upgrade','pip')
run(python,'-m','pip','install','--only-binary=:all:','PySide6>=6.8,<6.12','numpy>=1.26,<3')
run(python,'-c','import numpy; from PySide6.QtWidgets import QApplication; from PySide6.QtSvg import QSvgRenderer; '
    'from PySide6.QtPdf import QPdfDocument; from PySide6.QtPdfWidgets import QPdfView; '
    'from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput,QAudioBufferOutput; '
    'from PySide6.QtMultimediaWidgets import QVideoWidget; print("Orbit runtime imports OK")')
# Shell quoting is kept separate from .desktop quoting. Source paths may contain spaces.
launcher='#!/bin/bash\n# Generated by Orbit Explorer install.sh\n'
if platform=='Darwin':launcher+='export PATH=/opt/homebrew/bin:/usr/local/bin:"$PATH"\n'
launcher+='cd '+shlex.quote(str(source))+'\nexec '+shlex.quote(str(python))+' '+shlex.quote(str(source/'app.py'))+' "$@"\n'
command=home/'.local/bin/orbit-explorer'
if command.exists() and b'Generated by Orbit Explorer install.sh' not in command.read_bytes():
    fail(f'An unrelated command already exists at {command}; choose another location before installing.')
write(command,launcher,0o755)
if platform=='Linux':
    def desktop_quote(value):
        return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')+'"'
    entry=state.parent/'applications/orbit-explorer.desktop'
    # Do not replace the older unmarked launcher for a different source folder.
    if entry.exists() and '# Generated by Orbit Explorer install.sh' not in entry.read_text():
        entry=state.parent/'applications/orbit-explorer-managed.desktop'
    text='# Generated by Orbit Explorer install.sh\n[Desktop Entry]\nType=Application\nName=Orbit Explorer\n'
    text+='Comment=Spatial file explorer\nExec='+desktop_quote(command)+'\nIcon='+str(source/'assets/orbit.svg')+'\n'
    text+='Terminal=false\nCategories=System;FileManager;\nStartupNotify=true\n'
    write(entry,text)
    if shutil.which('update-desktop-database'):run('update-desktop-database',entry.parent)
    print('Linux uses the system plocate database. PipeWire routing uses your existing session; no session-manager/compositor configuration was changed.')
else:
    app=home/'Applications/Orbit Explorer.app'
    marker=app/'Contents/orbit-installer.json'
    if app.exists() and not marker.exists():fail(f'An unrelated app already exists at {app}. Move it aside before installing.')
    write(app/'Contents/MacOS/Orbit',launcher,0o755)
    plist={'CFBundleName':'Orbit Explorer','CFBundleDisplayName':'Orbit Explorer',
           'CFBundleIdentifier':'io.github.orbitexplorer.Orbit','CFBundleExecutable':'Orbit',
           'CFBundlePackageType':'APPL','CFBundleVersion':version,'CFBundleShortVersionString':version,
           'LSMinimumSystemVersion':'15.0','NSHighResolutionCapable':True}
    write(app/'Contents/Info.plist',plistlib.dumps(plist))
    write(marker,json.dumps({'source':str(source),'runtime':str(venv)},indent=2))
    register=Path('/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister')
    if register.exists():run(register,'-f',app)
    print(f'Mac launcher: {app}\nSearch uses existing Spotlight. File access permissions may need to be granted in System Settings.')
print(f'Installed. Open Orbit Explorer from your application menu or run {command}.')
print('Keep the source folder in place. Settings were not modified.')
print('To refresh a Git installation: bash '+shlex.quote(str(Path(os.environ.get('ORBIT_INSTALL_SCRIPT',str(source/'install.sh')))))+' --source '+shlex.quote(str(source))+' --update')
PY
