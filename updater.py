"""Install a downloaded Orbit release without nesting or replacing user data.

Only Python's standard library is needed. Packages are read as data; no script
from an incoming ZIP is executed. SHA-256 checks detect damaged packages, not
publisher identity: install ZIPs obtained from a trusted source.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import uuid
import zipfile

from install_lock import LOCK_NAME, PENDING_NAME, lock_installation

MANIFEST = "orbit-release.json"
BACKUPS = ".orbit-backups"
MAX_BYTES = 128 * 1024 * 1024
MAX_FILES = 4096
LEGACY_FILES = {
    "README.md", "app.py", "appearance.py", "assets/orbit.svg", "commandbar.py",
    "core.py", "graph.py", "install-desktop.sh", "interactions.py", "media.py",
    "metadata.py", "routing.py", "run.sh", "search_query.py", "search_worker.py",
    "thumbnails.py", "ui.py", "workspace.py", "tests/test_03.py",
    "tests/test_core.py", "tests/test_revision.py", "tests/test_ui.py",
}
REQUIRED = {"app.py", "core.py", "graph.py", "run.sh", "updater.py", "update.sh", "install_lock.py", LOCK_NAME}


class UpdateError(RuntimeError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(name: str, *, directory: bool = False) -> str:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise UpdateError(f"Invalid package path: {name!r}")
    value = name.removesuffix("/") if directory else name
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts) or PurePosixPath(value).is_absolute():
        raise UpdateError(f"Unsafe package path: {name!r}")
    if any(part.startswith(".") and not (index == len(parts)-1 and part == LOCK_NAME)
           for index, part in enumerate(parts)):
        raise UpdateError(f"Reserved package path: {name!r}")
    return value


def checked_path(root: Path, name: str) -> Path:
    """Reject links and directory/file collisions inside an installation."""
    safe_name(name)
    path = root
    pieces = PurePosixPath(name).parts
    for index, piece in enumerate(pieces):
        path /= piece
        if path.is_symlink():
            raise UpdateError(f"Refusing to follow a symbolic link: {path}")
        if path.exists() and (not path.is_file() if index == len(pieces)-1 else not path.is_dir()):
            raise UpdateError(f"Unexpected file or directory at {path}")
    return path


def manifest_from(raw: bytes) -> dict:
    try:
        if len(raw) > 1024 * 1024:
            raise ValueError("manifest too large")
        info = json.loads(raw)
        if info["application"] != "orbit-explorer" or info["format"] != 1:
            raise ValueError("not an Orbit package")
        if not re.fullmatch(r"\d+\.\d+\.\d+", info["version"]):
            raise ValueError("invalid version")
        files = info["files"]
        if not isinstance(files, dict) or not REQUIRED <= files.keys() or len(files) > MAX_FILES:
            raise ValueError("missing required program files")
        for name, record in files.items():
            safe_name(name)
            if name == MANIFEST:
                raise ValueError("manifest cannot list itself")
            if record["mode"] not in (0o644, 0o755) or not re.fullmatch("[0-9a-f]{64}", record["sha256"]):
                raise ValueError("invalid file metadata")
            if type(record["size"]) is not int or record["size"] < 0:
                raise ValueError("invalid file size")
            if any(str(parent) in files for parent in PurePosixPath(name).parents if str(parent) != "."):
                raise ValueError("overlapping file paths")
        if sum(record["size"] for record in files.values()) > MAX_BYTES:
            raise ValueError("package too large")
        return info
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise UpdateError(f"Invalid Orbit release manifest: {error}") from error


@dataclass
class Release:
    info: dict
    files: dict[str, bytes]
    manifest: bytes

    @classmethod
    def load(cls, source: Path) -> "Release":
        source = source.expanduser().resolve()
        if source.is_dir():
            raw = checked_path(source, MANIFEST).read_bytes()
            info = manifest_from(raw)
            files = {}
            for name, record in info["files"].items():
                path = checked_path(source, name)
                if path.stat().st_size != record["size"]:
                    raise UpdateError(f"Damaged release file: {name}")
                files[name] = path.read_bytes()
        else:
            try:
                with zipfile.ZipFile(source) as archive:
                    members = archive.infolist()
                    if len(members) > MAX_FILES * 2 or sum(m.file_size for m in members) > MAX_BYTES + 1024*1024:
                        raise UpdateError("The ZIP is too large to be an Orbit release.")
                    seen = set()
                    for member in members:
                        safe_name(member.orig_filename, directory=member.is_dir())
                        kind = stat.S_IFMT(member.external_attr >> 16)
                        if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or member.flag_bits & 1:
                            raise UpdateError("ZIP links, special files, and encrypted entries are unsupported.")
                        if member.filename in seen:
                            raise UpdateError(f"Duplicate ZIP entry: {member.filename}")
                        seen.add(member.filename)
                    manifests = [m.filename for m in members if not m.is_dir() and PurePosixPath(m.filename).name == MANIFEST]
                    if len(manifests) != 1 or len(PurePosixPath(manifests[0]).parts) > 2:
                        raise UpdateError("Choose an Orbit release ZIP containing orbit-release.json.")
                    prefix = manifests[0][:-len(MANIFEST)]
                    raw = archive.read(manifests[0]); info = manifest_from(raw)
                    expected = {prefix+name for name in info["files"]} | {prefix+MANIFEST}
                    if {m.filename for m in members if not m.is_dir()} != expected:
                        raise UpdateError("ZIP contents do not match the release manifest.")
                    files = {name: archive.read(prefix+name) for name in info["files"]}
            except (zipfile.BadZipFile, NotImplementedError) as error:
                raise UpdateError(f"Unreadable update ZIP: {error}") from error
        for name, record in info["files"].items():
            if len(files[name]) != record["size"] or digest(files[name]) != record["sha256"]:
                raise UpdateError(f"Checksum mismatch: {name}. Download the release again.")
        if files[LOCK_NAME]:
            raise UpdateError("The installation lock must be empty.")
        return cls(info, files, raw)


def installed_info(target: Path) -> tuple[str, set[str]]:
    path = checked_path(target, MANIFEST)
    if path.exists():
        info = manifest_from(path.read_bytes())
        return info["version"], set(info["files"]) | {MANIFEST}
    version = "0.0.0"
    readme = checked_path(target, "README.md")
    if readme.exists():
        match = re.search(r"Orbit Explorer (\d+)\.(\d+)(?:\.(\d+))?", readme.read_text(errors="replace"))
        if match:
            version = ".".join(part or "0" for part in match.groups())
    return version, {name for name in LEGACY_FILES if checked_path(target, name).exists()}


def legacy_processes(target: Path, proc_root: Path = Path("/proc")) -> list[int]:
    """Also recognize pre-updater Orbit instances that do not hold our lock."""
    found = []
    for proc in proc_root.glob("[0-9]*"):
        try:
            if int(proc.name) == os.getpid():
                continue
            args = (proc / "cmdline").read_bytes().split(b"\0")
            if not args or "python" not in Path(os.fsdecode(args[0])).name.lower():
                continue
            for arg in args[1:]:
                script = Path(os.fsdecode(arg))
                if script.name != "app.py":
                    continue
                if not script.is_absolute():
                    script = (proc / "cwd").resolve() / script
                if script.resolve() == target / "app.py":
                    found.append(int(proc.name)); break
        except (OSError, ValueError):
            continue
    return found


@contextmanager
def exclusive_installation(target: Path):
    if not target.is_dir() or not all((target/name).is_file() for name in ("app.py", "core.py", "graph.py", "run.sh")):
        raise UpdateError(f"No existing Orbit installation at {target}. Use --target /path/to/orbit-explorer.")
    descriptor = lock_installation(target)
    try:
        running = legacy_processes(target)
        if running:
            raise UpdateError(f"Close Orbit before updating (running process IDs: {', '.join(map(str, running))}).")
        yield
    finally:
        os.close(descriptor)


def sync_directory(path: Path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: Path, data: bytes, mode=0o644, owner=None):
    """Write and fsync beside the destination before replacing its inode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".orbit-write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data); stream.flush()
            os.fchmod(stream.fileno(), mode)
            if os.geteuid() == 0 and owner is not None:
                os.fchown(stream.fileno(), *owner)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def private_directory(path: Path):
    if path.is_symlink() or path.exists() and not path.is_dir():
        raise UpdateError(f"Invalid updater directory: {path}")
    path.mkdir(mode=0o700, exist_ok=True)


def load_backup(backup: Path, target: Path) -> tuple[dict, dict[str, bytes]]:
    if (backup.is_symlink() or backup.parent != target / BACKUPS
            or backup.parent.is_symlink() or (backup / "files").is_symlink()):
        raise UpdateError("Choose a backup inside this installation's .orbit-backups directory.")
    try:
        record = json.loads(checked_path(backup, "record.json").read_bytes())
        if record["target"] != str(target) or record["format"] != 1:
            raise ValueError("backup belongs to another installation")
        files = {}
        for name, previous in record["files"].items():
            checked_path(target, name)
            if name == LOCK_NAME or name not in record["touched"]:
                raise ValueError("invalid backup entry")
            path = checked_path(backup / "files", name)
            data = path.read_bytes()
            if digest(data) != previous["sha256"]:
                raise ValueError(f"damaged backup file: {name}")
            files[name] = data
        for name in record["touched"]:
            checked_path(target, name)
            if name == LOCK_NAME:
                raise ValueError("invalid backup entry")
            check_bytecode(target, name)
        for name in record["created_dirs"]:
            safe_name(name)
        return record, files
    except (ValueError, KeyError, TypeError) as error:
        raise UpdateError(f"Invalid rollback backup: {error}") from error


def restore_files(backup: Path, target: Path):
    record, files = load_backup(backup, target)
    for name in reversed(record["touched"]):
        destination = checked_path(target, name)
        if name in files:
            previous = record["files"][name]
            atomic_write(destination, files[name], previous["mode"], (previous["uid"], previous["gid"]))
            os.utime(destination, ns=(previous["atime_ns"], previous["mtime_ns"]))
        elif destination.exists():
            destination.unlink(); sync_directory(destination.parent)
    for name in sorted(record["created_dirs"], key=lambda n:len(PurePosixPath(n).parts), reverse=True):
        try:
            (target / name).rmdir()
        except OSError:
            pass  # A user-created file in that folder must survive rollback.
    clear_bytecode(target, record["touched"])
    (target / PENDING_NAME).unlink(missing_ok=True)
    sync_directory(target)


def check_bytecode(target: Path, name: str):
    path = target / name
    if path.suffix == ".py" and (path.parent / "__pycache__").is_symlink():
        raise UpdateError(f"Refusing a symbolic link for Python's cache: {path.parent / '__pycache__'}")


def clear_bytecode(target: Path, names):
    """Avoid stale timestamp-based caches when releases share size/mtime."""
    for name in names:
        path = target / name
        if path.suffix != ".py":
            continue
        cache = path.parent / "__pycache__"
        check_bytecode(target, name)
        if cache.is_dir():
            for compiled in cache.glob(path.stem+".*.pyc"):
                compiled.unlink()


def recover_pending(target: Path, report=print) -> bool:
    pending = target / PENDING_NAME
    if pending.is_symlink():
        raise UpdateError("The update recovery marker must not be a symbolic link.")
    if not pending.exists():
        return False
    try:
        name = json.loads(pending.read_bytes())["backup"]
        if not re.fullmatch(r"[0-9TZ-]+-[a-f0-9]{8}", name):
            raise ValueError("invalid backup name")
    except (KeyError, TypeError, ValueError) as error:
        raise UpdateError(f"Cannot read the update recovery marker: {error}") from error
    restore_files(target / BACKUPS / name, target)
    report("Recovered the previous installation from an interrupted update.")
    return True


def apply_release(release: Release, target: Path, *, allow_downgrade=False, report=print) -> Path | None:
    target = target.expanduser().resolve()
    with exclusive_installation(target):
        recover_pending(target, report)
        old_version, owned = installed_info(target)
        if not allow_downgrade and tuple(map(int, release.info["version"].split("."))) < tuple(map(int, old_version.split("."))):
            raise UpdateError("This release is older than the installed version. Use --allow-downgrade intentionally, or --rollback BACKUP.")
        incoming = {**release.files, MANIFEST: release.manifest}
        incoming.pop(LOCK_NAME, None); owned.discard(LOCK_NAME)
        touched = sorted(owned | incoming.keys())
        changed = False
        for name in touched:
            destination = checked_path(target, name)
            check_bytecode(target, name)
            if name not in owned and destination.exists():
                raise UpdateError(f"A new program file would overwrite your unrelated file: {destination}. Move it aside first.")
            if name in incoming:
                mode = release.info["files"].get(name, {}).get("mode", 0o644)
                changed |= not destination.exists() or destination.read_bytes() != incoming[name] or stat.S_IMODE(destination.stat().st_mode) != mode
            else:
                changed |= destination.exists()
        if not changed:
            report(f"Orbit {release.info['version']} is already installed. No files changed.")
            return None
        report(f"Updating Orbit {old_version} → {release.info['version']} in {target}")
        private_directory(target / BACKUPS)
        backup = target / BACKUPS / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:8])
        backup.mkdir(mode=0o700)
        record = {"format":1, "target":str(target), "from_version":old_version,
                  "to_version":release.info["version"], "after_manifest":digest(release.manifest),
                  "touched":touched, "files":{}, "created_dirs":[]}
        created_dirs = set()
        # Complete and flush the backup before touching application files.
        for name in touched:
            path = checked_path(target, name)
            if path.exists():
                details = path.stat(); data = path.read_bytes()
                record["files"][name] = {"sha256":digest(data), "mode":stat.S_IMODE(details.st_mode),
                    "uid":details.st_uid, "gid":details.st_gid,
                    "mtime_ns":details.st_mtime_ns, "atime_ns":details.st_atime_ns}
                atomic_write(backup / "files" / name, data, stat.S_IMODE(details.st_mode))
            for parent in PurePosixPath(name).parents:
                if str(parent) != "." and not (target / parent).exists():
                    created_dirs.add(str(parent))
        record["created_dirs"] = sorted(created_dirs)
        atomic_write(backup / "record.json", json.dumps(record, indent=2).encode())
        atomic_write(target / PENDING_NAME, json.dumps({"backup":backup.name}).encode())
        try:
            for name in touched:
                path = checked_path(target, name)
                if name in incoming:
                    mode = release.info["files"].get(name, {}).get("mode", 0o644)
                    previous = path.stat() if path.exists() else target.stat()
                    atomic_write(path, incoming[name], mode, (previous.st_uid, previous.st_gid))
                elif path.exists():
                    path.unlink(); sync_directory(path.parent)
            clear_bytecode(target, touched)
            (target / PENDING_NAME).unlink(); sync_directory(target)
        except BaseException as error:
            try:
                restore_files(backup, target)
            except BaseException as recovery:
                raise UpdateError(f"Update interrupted: {error}. Recovery also failed: {recovery}. Free disk space/fix permissions, then run update.sh --target '{target}' --recover. Backup: {backup}") from error
            raise UpdateError(f"Update failed; previous application files were restored. Reason: {error}") from error
        report(f"Installed Orbit {release.info['version']}. Settings and unrelated files were preserved.")
        report(f"Rollback backup: {backup}")
        return backup


def rollback(backup: Path, target: Path, report=print):
    target = target.expanduser().resolve(); backup = backup.expanduser().absolute()
    with exclusive_installation(target):
        recover_pending(target, report)
        record, _ = load_backup(backup, target)
        manifest = checked_path(target, MANIFEST)
        if not manifest.exists() or digest(manifest.read_bytes()) != record["after_manifest"]:
            raise UpdateError("This backup is not for the currently installed release. Choose the most recent update's backup.")
        atomic_write(target / PENDING_NAME, json.dumps({"backup":backup.name}).encode())
        restore_files(backup, target)
        report(f"Restored Orbit {record['from_version']}. Settings and unrelated files were preserved.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Update Orbit in place from a trusted downloaded ZIP or this extracted release.")
    parser.add_argument("archive", nargs="?", type=Path, help="downloaded Orbit release ZIP; omit to install this extracted release")
    parser.add_argument("--target", type=Path, help="existing installation (default: /orbit-explorer for a bundled update; this script's folder for a ZIP)")
    parser.add_argument("--allow-downgrade", action="store_true")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--rollback", type=Path, metavar="BACKUP", help="restore the backup from the last update")
    action.add_argument("--recover", action="store_true", help="repair an interrupted update, then exit")
    args = parser.parse_args(argv)
    folder = Path(__file__).resolve().parent
    target = (args.target or (folder if args.archive or args.rollback or args.recover else Path("/orbit-explorer"))).expanduser().resolve()
    if args.archive and (args.rollback or args.recover):
        parser.error("Choose either an update archive or recovery/rollback.")
    try:
        if args.rollback:
            rollback(args.rollback, target)
        elif args.recover:
            with exclusive_installation(target):
                if not recover_pending(target):
                    print("No interrupted update needs recovery.")
        else:
            apply_release(Release.load(args.archive or folder), target, allow_downgrade=args.allow_downgrade)
        print(f"Start Orbit using: {target / 'run.sh'}")
        return 0
    except (OSError, RuntimeError, KeyboardInterrupt) as error:
        print(f"Orbit updater: {error}", file=sys.stderr)
        if isinstance(error, PermissionError):
            print("The installation is not writable. For a root-owned install, run only update.sh with sudo; launch Orbit as your normal user.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
