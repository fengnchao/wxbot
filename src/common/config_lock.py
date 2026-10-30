"""Cross-process lock for configuration writers (dashboard and butler share it)."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import threading

_LOCK = threading.RLock()


def edit_lock_path(path):
    target = Path(path).resolve()
    identity = os.path.normcase(str(target))
    digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()
    return target.parent / 'data' / 'cache' / 'config-locks' / (digest + '.lock')


@contextmanager
def config_lock(path):
    """Serialize dashboard and butler writers on the same configuration file."""
    with _LOCK:
        lockpath = edit_lock_path(path)
        lockpath.parent.mkdir(parents=True, exist_ok=True)
        with lockpath.open('a+b') as fh:
            if fh.tell() == 0:
                fh.write(b'\0')
                fh.flush()
            fh.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fh.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fh, fcntl.LOCK_UN)
