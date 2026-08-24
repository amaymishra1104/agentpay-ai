from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Iterator


# Protects only the atomic filesystem operation.
# It must NOT be held while waiting for another owner,
# otherwise the owning thread cannot finish and release its lock.
_THREAD_LOCK = Lock()


def is_pid_running(pid: int) -> bool:
    """
    Return True when pid belongs to a currently running process.

    os.kill(pid, 0) checks whether the process exists without
    terminating it.
    """
    if pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    else:
        return True


def _read_lock_pid(lock_path: Path) -> int | None:
    """Read the PID stored in a lock file."""
    try:
        text = lock_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None

    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _remove_lock(lock_path: Path) -> None:
    """Remove a lock file if it exists."""
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _try_remove_stale_lock(lock_path: Path) -> bool:
    """
    Remove a lock when its recorded PID is no longer alive.

    Returns True if the lock was removed or is already absent.
    Returns False if the lock still belongs to a live process.
    """
    if not lock_path.exists():
        return True

    pid = _read_lock_pid(lock_path)

    # Corrupt/malformed lock files are considered stale.
    if pid is None:
        _remove_lock(lock_path)
        return not lock_path.exists()

    if not is_pid_running(pid):
        _remove_lock(lock_path)
        return not lock_path.exists()

    return False


@contextmanager
def file_lock(
    lock_path: Path,
    timeout: float = 10.0,
    delay: float = 0.01,
) -> Iterator[None]:
    """
    Cross-process file lock with stale/dead-PID recovery.

    The lock file contains the PID of the process holding the lock.

    Important:
    - Atomic acquisition uses exclusive file creation.
    - The in-process mutex is held ONLY during the filesystem
      acquisition attempt.
    - The mutex is released before waiting.
    - A live owner's lock is never stolen.
    - A dead owner's lock can be recovered.
    - The owning context removes its lock on exit.
    """

    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if timeout < 0:
        raise ValueError("timeout must be >= 0")

    if delay <= 0:
        delay = 0.01

    deadline = time.monotonic() + timeout
    pid = os.getpid()

    while True:
        acquired = False

        # Only protect the atomic create operation.
        #
        # DO NOT hold this mutex while sleeping/waiting. Another thread
        # may already own the filesystem lock and must be allowed to reach
        # its finally block and remove it.
        with _THREAD_LOCK:
            try:
                with lock_path.open("x", encoding="utf-8") as lock_file:
                    lock_file.write(str(pid))
                    lock_file.flush()
                    os.fsync(lock_file.fileno())

                acquired = True

            except FileExistsError:
                acquired = False

        if acquired:
            break

        # The file exists. Check whether its owner is actually dead.
        #
        # NOTE:
        # Threads in the same process have the same PID. Therefore a lock
        # owned by another thread in this process is correctly treated as
        # belonging to a live process and is NOT deleted.
        _try_remove_stale_lock(lock_path)

        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Timed out waiting for file lock: {lock_path}"
            )

        time.sleep(delay)

    try:
        yield
    finally:
        # Only the process that owns the PID may remove the lock.
        current_pid = _read_lock_pid(lock_path)

        if current_pid == pid:
            _remove_lock(lock_path)