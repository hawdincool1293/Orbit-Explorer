"""Keep running Orbit instances and its updater out of each other's way."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import stat

LOCK_NAME = ".orbit-install.lock"
PENDING_NAME = ".orbit-update-pending.json"


def lock_installation(folder: Path, *, shared: bool = False) -> int:
    """Return an open, locked descriptor. Never replace or unlink this file."""
    descriptor = os.open(folder / LOCK_NAME,
                         os.O_RDONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o644)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise RuntimeError("The Orbit installation lock must be a regular file.")
        fcntl.flock(descriptor, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        if shared and ((folder / PENDING_NAME).exists() or (folder / PENDING_NAME).is_symlink()):
            raise RuntimeError("An interrupted update needs recovery. Run update.sh --recover first.")
    except BlockingIOError as error:
        os.close(descriptor)
        message = "Orbit is being updated." if shared else "Close every Orbit window before updating. Another updater may also be running."
        raise RuntimeError(message) from error
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor
