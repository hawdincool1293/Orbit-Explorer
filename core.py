"""Filesystem model and indexing adapters for Orbit.

Only the currently visible neighbourhood is read. Computer-wide lookup is
delegated to plocate; this application does not maintain a second index.
"""
from __future__ import annotations

import math
import os
import shutil
import stat
import subprocess
import json
import mimetypes
from desktop_backend import IS_MAC,run_host,mac_drives
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Node:
    path: str
    name: str
    directory: bool
    size: int
    depth: int
    xyz: tuple[float, float, float]
    parent: str | None
    kind: str = ""
    modified_ns: int = 0


def _entries(path: str, show_hidden: bool = False):
    try:
        with os.scandir(path) as iterator:
            items = []
            for entry in iterator:
                if entry.name.startswith(".") and not show_hidden:
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                        items.append((entry, info))
                except OSError:
                    continue
            return sorted(items, key=lambda e: (not stat.S_ISDIR(e[1].st_mode), e[0].name.casefold()))
    except OSError:
        return []


def _sphere(i: int, n: int, radius: float) -> tuple[float, float, float]:
    # A Fibonacci sphere spaces siblings evenly and stays stable for a scan.
    y = 1 - 2 * (i + 0.5) / max(n, 1)
    angle = i * math.pi * (3 - math.sqrt(5))
    spread = math.sqrt(max(0, 1 - y * y))
    return radius * spread * math.cos(angle), radius * y, radius * spread * math.sin(angle)


def scan_neighbourhood(root: str, limit: int = 680, show_hidden: bool = False, spacing: float = 1.35) -> tuple[list[Node], int]:
    """Return a bounded local graph and number of undisplayed children."""
    root = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(root):
        raise NotADirectoryError(root)
    top = _entries(root, show_hidden)
    remaining = max(0, len(top) - min(len(top), limit - 1))
    top = top[: max(0, limit - 1)]
    immediate_size = sum(info.st_size for _, info in top)
    nodes = [Node(root, os.path.basename(root) or root, True, immediate_size, 0, (0, 0, 0), None, modified_ns=os.stat(root).st_mtime_ns)]
    for i, (entry, info) in enumerate(top):
        directory = stat.S_ISDIR(info.st_mode)
        origin = _sphere(i, len(top), spacing * (260 + math.sqrt(len(top)) * 15))
        child_budget = min(42, max(0, limit - len(nodes) - (len(top) - i)))
        children = _entries(entry.path, show_hidden) if directory and child_budget else []
        # Reserve a slot for each remaining sibling before adding grandchildren.
        visible = min(len(children), child_budget)
        size = sum(child_info.st_size for _, child_info in children) if directory and children else info.st_size
        nodes.append(Node(entry.path, entry.name, directory, size, 1, origin, root, modified_ns=info.st_mtime_ns))
        remaining += len(children) - visible
        for j, (child, child_info) in enumerate(children[:visible]):
            offset = _sphere(j, visible, spacing * (70 + math.sqrt(visible) * 13))
            xyz = tuple(origin[k] + offset[k] for k in range(3))
            nodes.append(Node(child.path, child.name, stat.S_ISDIR(child_info.st_mode), child_info.st_size, 2, xyz, entry.path, modified_ns=child_info.st_mtime_ns))
    return nodes, remaining


def node_radius(node: Node) -> float:
    # Logarithmic scaling preserves distinctions without letting huge files
    # obscure their neighbours. Directory nodes have a minimum hub size.
    return min(25.0, (9 if node.directory else 3.5) + 1.45 * math.log2(1 + max(0, node.size) / 4096))


def path_journey(source: str, target: str) -> list[str]:
    """Directories on a route through the closest shared ancestor."""
    source = os.path.abspath(source)
    target = os.path.abspath(target)
    destination = target if os.path.isdir(target) else os.path.dirname(target)
    common = os.path.commonpath([source, destination])
    route: list[str] = []
    here = source
    while here != common:
        here = os.path.dirname(here)
        route.append(here)
    down = []
    here = destination
    while here != common:
        down.append(here)
        here = os.path.dirname(here)
    route.extend(reversed(down))
    return route or [destination]


def search_files(query: str, maximum: int = 90) -> list[str]:
    """Use plocate's existing index; never shell-interpolate a query."""
    if IS_MAC:
        from desktop_backend import index_command
        from search_query import Query
        if not query.strip():return []
        result=run_host(index_command(Query(name=query.strip())),capture_output=True,timeout=15)
        if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
        return [os.fsdecode(p) for p in result.stdout.split(b'\0') if p and os.path.exists(os.fsdecode(p))][:maximum]
    if not shutil.which("plocate"):
        raise RuntimeError("plocate is missing. Install the CachyOS/Arch plocate package and enable its updatedb timer.")
    if not query.strip():
        return []
    command = ["plocate", "-0", "-i", "-l", str(maximum), "--", query.strip()]
    result = subprocess.run(command, capture_output=True, timeout=15, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.decode(errors="replace").strip() or "plocate index is unavailable")
    return [os.fsdecode(raw) for raw in result.stdout.split(b"\0") if raw and os.path.exists(os.fsdecode(raw))]


def drive_inventory(payload: dict) -> list[dict]:
    """Group partitions under physical disks; exclude virtual RAM/loop devices."""
    def convert(item):
        return {"path": item.get("path", ""), "name": item.get("label") or item.get("name", "Drive"),
                "model": (item.get("model") or "").strip(), "size": item.get("size", ""),
                "serial": (item.get('serial') or '').strip(),"wwn":(item.get('wwn') or '').strip(),"uuid":item.get('uuid') or '',
                "mount": item.get("mountpoint") or "", "type": item.get("type", ""),
                "fs": item.get("fstype") or "", "removable": bool(item.get("rm")),
                "children": [convert(c) for c in (item.get("children") or [])]}
    return [convert(b) for b in payload.get("blockdevices", [])
            if b.get("type") in ("disk", "rom") and not b.get("name", "").startswith(("zram", "loop", "ram"))]


def visible_mounts() -> list[dict]:
    if IS_MAC:return mac_drives()
    """One record per physical drive, retaining its partition hierarchy."""
    if not shutil.which("lsblk") and not os.environ.get('FLATPAK_ID'):
        return []
    result = run_host(["lsblk", "-J", "-o", "NAME,PATH,LABEL,MODEL,SERIAL,WWN,UUID,TYPE,SIZE,MOUNTPOINT,FSTYPE,RM"],
                            capture_output=True, text=True, timeout=8, check=True)
    return drive_inventory(json.loads(result.stdout))

def drive_key(drive):
    for key in ('wwn','serial','uuid'):
        if drive.get(key):return key+':'+drive[key]
    return 'device:'+drive['path']

def drive_name(drive,config):
    return config.get('drive_aliases',{}).get(drive_key(drive)) or drive.get('model') or drive.get('name') or drive['path']


def mount_device(device: str, mounted: bool, unlock: bool = False) -> str:
    if IS_MAC:
        if unlock:raise RuntimeError('Unlock encrypted macOS volumes in Disk Utility first.')
        result=run_host(['/usr/sbin/diskutil','unmount' if mounted else 'mount',device],capture_output=True,text=True)
        if result.returncode:raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()
    if not shutil.which("udisksctl") and not os.environ.get('FLATPAK_ID'):
        raise RuntimeError("udisksctl is unavailable; install udisks2.")
    result = run_host(["udisksctl", "unlock" if unlock else ("unmount" if mounted else "mount"), "-b", device],
                            capture_output=True, text=True, timeout=120, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Drive operation failed")
    return result.stdout.strip()


def drive_graph(drive):
    """Partitions are graph nodes, never sidebar rows."""
    nodes, devices = [], {}
    def add(item, parent, depth, xyz):
        path = item["path"]
        devices[path] = item
        name = item.get('display_name') or ((item["model"] or item["name"]) if depth == 0 else item["name"])
        nodes.append(Node(path, name, False, 0, depth, xyz, parent, "drive" if depth == 0 else "partition"))
        for i, child in enumerate(item["children"]):
            delta = _sphere(i, len(item["children"]), 215 if depth == 0 else 80)
            add(child, path, depth + 1, tuple(xyz[j] + delta[j] for j in range(3)))
    add(drive, None, 0, (0, 0, 0))
    return nodes, devices


def file_category(path: str, directory=False) -> str:
    if directory: return "folder"
    mime = mimetypes.guess_type(path)[0] or ""
    suffix = Path(path).suffix.lower()
    if mime.startswith("image/"): return "image"
    if mime.startswith("video/"): return "video"
    if mime.startswith("audio/") or suffix in (".flac", ".opus", ".m4a"): return "audio"
    if mime.startswith("text/") or suffix in (".md", ".log", ".doc", ".docx", ".odt", ".rtf", ".pdf"): return "document"
    if suffix in (".zip", ".7z", ".tar", ".gz", ".xz", ".rar"): return "archive"
    return "file"


def transfer_plan(paths, destination, link=False):
    """Preflight a batch. Never overwrite a collision or move into oneself."""
    destination = os.path.abspath(os.path.expanduser(destination))
    if not os.path.isdir(destination): raise ValueError("Choose an existing destination directory.")
    roots = sorted(set(os.path.abspath(p) for p in paths), key=lambda p: (len(Path(p).parts), p))
    chosen = []
    for p in roots:
        if not os.path.lexists(p): raise FileNotFoundError(p)
        if any(os.path.commonpath([p, parent]) == parent and os.path.isdir(parent) and not os.path.islink(parent)
               for parent in chosen): continue
        if p == "/": raise ValueError("The filesystem root cannot be transferred.")
        chosen.append(p)
    plan, outputs = [], set()
    for source in chosen:
        if not link and os.path.isdir(source) and not os.path.islink(source):
            real_source, real_dest = os.path.realpath(source), os.path.realpath(destination)
            if os.path.commonpath([real_source, real_dest]) == real_source:
                raise ValueError("A folder cannot be transferred into itself.")
        output = os.path.join(destination, os.path.basename(source))
        if os.path.lexists(output) or output in outputs:
            raise FileExistsError(f"Destination already contains {os.path.basename(source)}. Nothing was transferred.")
        outputs.add(output); plan.append((source, output))
    return plan


def transfer_files(paths, destination, copy=False, *, action=None):
    action = action or ('copy' if copy else 'move')
    if action not in ('copy','move','link'): raise ValueError('Choose Move, Copy, or Link.')
    plan = transfer_plan(paths, destination, link=action=='link')
    completed = []
    for source, output in plan:
        try:
            if action=='link':
                os.symlink(source,output,target_is_directory=os.path.isdir(source))
            elif action=='copy':
                if os.path.isdir(source) and not os.path.islink(source):
                    shutil.copytree(source, output, symlinks=True)
                elif os.path.islink(source):
                    os.symlink(os.readlink(source),output)
                else:
                    with open(source,"rb") as incoming, open(output,"xb") as outgoing:
                        shutil.copyfileobj(incoming,outgoing,1024*1024)
                    shutil.copystat(source,output,follow_symlinks=False)
            else:
                # GNU mv handles cross-device moves and refuses a collision
                # even if it appears after preflight. -T treats output as the
                # exact destination, never as a folder to silently nest into.
                result=subprocess.run(['mv','-n',source,output] if IS_MAC else ['mv','-n','-T','--',source,output],capture_output=True,text=True)
                if result.returncode or os.path.lexists(source):
                    raise OSError(result.stderr.strip() or f'Could not move {source}; destination may already exist.')
            completed.append((source, output))
        except Exception as exc:
            return completed, f"{len(completed)} of {len(plan)} transferred. {exc}"
    return completed, ""
