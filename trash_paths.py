"""Local freedesktop Trash locations; never hand trash URLs to a browser."""
import os,stat,shutil
from desktop_backend import IS_MAC
from pathlib import Path

def home_trash():
    if IS_MAC:return Path.home()/'.Trash'
    if os.environ.get('FLATPAK_ID'):return Path.home()/'.local/share/Trash/files'
    configured=os.environ.get('XDG_DATA_HOME','')
    data=Path(configured) if configured and os.path.isabs(configured) else Path.home()/'.local/share'
    return data/'Trash'/'files'

def trash_locations(drives=()):
    result=[('Home Trash',home_trash())];uid=os.getuid();seen={str(result[0][1])}
    def walk(items):
        for item in items:
            mount=item.get('mount','')
            if mount:
                base=Path(mount)
                for candidate in ((base/'.Trashes'/str(uid),) if IS_MAC else (base/'.Trash'/str(uid),base/f'.Trash-{uid}')):
                    try:
                        info=candidate.lstat();files=candidate if IS_MAC else candidate/'files'
                        if stat.S_ISDIR(info.st_mode) and info.st_uid==uid and files.is_dir() and not files.is_symlink() and str(files) not in seen:
                            result.append((f'{item.get("name") or mount} Trash',files));seen.add(str(files))
                    except OSError:pass
            walk(item.get('children',()))
    walk(drives);return result

def containing_trash(path,roots):
    path=Path(os.path.abspath(path))
    for root in roots:
        root=Path(root).resolve()
        # Resolve parents only: a symlink entry may point outside Trash and must
        # be unlinked without ever following its target.
        try:
            actual=path.parent.resolve()/path.name
            actual.relative_to(root)
            if actual!=root:return root,actual
        except ValueError:pass
    return None

def delete_trashed(paths,roots):
    checked=[]
    for path in paths:
        item=containing_trash(path,roots)
        if not item:raise ValueError('Permanent deletion is limited to items inside detected Trash folders.')
        checked.append(item)
    completed=[]
    for root,path in sorted(checked,key=lambda item:len(item[1].parts)):
        if any(path.is_relative_to(parent) for parent in completed):continue
        mode=path.lstat().st_mode
        if stat.S_ISDIR(mode):
            if os.path.ismount(path):raise ValueError('A mounted filesystem cannot be permanently deleted.')
            shutil.rmtree(path)
        else:path.unlink()
        if not IS_MAC and path.parent==root:
            info=root.parent/'info'
            if info.is_dir() and not info.is_symlink():(info/(path.name+'.trashinfo')).unlink(missing_ok=True)
        completed.append(path)
    return [str(p) for p in completed]
