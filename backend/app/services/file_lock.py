from __future__ import annotations

import os
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psutil


DEFAULT_TIMEOUT = 10.0
DEFAULT_DELAY = 0.01

# Windows can briefly refuse access to a file while another thread/process
# has an open handle. This is specifically ERROR_SHARING_VIOLATION (32).
#
# We retry only this condition. Other filesystem errors remain failures.
WINDOWS_SHARING_VIOLATION = 32
LOCK_IO_MAX_ATTEMPTS = 30
LOCK_IO_RETRY_DELAY = 0.005


def _is_windows_sharing_violation(
    exc: OSError,
) -> bool:
    """
    Return True only for Windows ERROR_SHARING_VIOLATION.

    Windows uses WinError 32 when an operation such as unlink/read/open
    temporarily conflicts with another open file handle.

    This must remain narrowly scoped. Arbitrary OSError instances should
    not be retried because they may represent genuine filesystem failures.
    """
    return (
        sys.platform == "win32"
        and getattr(
            exc,
            "winerror",
            None,
        )
        == WINDOWS_SHARING_VIOLATION
    )


def _read_lock_owner(
    lock_path: Path,
) -> tuple[int, str] | None:
    """
    Read lock ownership metadata.

    Format:

        <pid>:<token>

    Legacy PID-only locks are also accepted:

        <pid>

    Returns None when the lock is missing, empty, malformed,
    or temporarily unreadable.

    On Windows, a short-lived sharing violation is retried because
    another thread may briefly have the lock file open while this
    thread is attempting to inspect it.
    """
    for attempt in range(
        LOCK_IO_MAX_ATTEMPTS,
    ):
        try:
            text = lock_path.read_text(
                encoding="ascii",
            ).strip()

            break

        except FileNotFoundError:
            return None

        except UnicodeError:
            return None

        except OSError as exc:
            if not _is_windows_sharing_violation(exc):
                return None

            if attempt == LOCK_IO_MAX_ATTEMPTS - 1:
                return None

            time.sleep(
                LOCK_IO_RETRY_DELAY,
            )

    else:
        return None

    if not text:
        return None

    parts = text.split(
        ":",
        1,
    )

    try:
        pid = int(parts[0])

    except (
        TypeError,
        ValueError,
    ):
        return None

    if pid <= 0:
        return None

    token = (
        parts[1]
        if len(parts) == 2
        else ""
    )

    return pid, token


def is_pid_running(
    pid: int,
) -> bool:
    """
    Return whether the OS currently has a process with this PID.

    This is used only for recovering locks whose owner metadata
    identifies a dead process.

    psutil.pid_exists() is used instead of os.kill(pid, 0) because
    Windows does not implement the POSIX "signal 0" liveness probe
    semantics. On Windows, os.kill() can terminate the target process.
    """
    if pid <= 0:
        return False

    return psutil.pid_exists(pid)


def _remove_lock(
    lock_path: Path,
) -> bool:
    """
    Best-effort removal of a lock.

    Returns True when the lock is confirmed absent.

    On Windows, ERROR_SHARING_VIOLATION can occur transiently when
    another thread/process briefly has the lock file open. That
    condition is retried for a short bounded period.

    Other OSError instances are not retried.
    """
    for attempt in range(
        LOCK_IO_MAX_ATTEMPTS,
    ):
        try:
            lock_path.unlink()

            return True

        except FileNotFoundError:
            return True

        except OSError as exc:
            if not _is_windows_sharing_violation(exc):
                return False

            if attempt == LOCK_IO_MAX_ATTEMPTS - 1:
                return False

            time.sleep(
                LOCK_IO_RETRY_DELAY,
            )

    return False


def _try_remove_stale_lock(
    lock_path: Path,
) -> bool:
    """
    Attempt safe recovery of an abandoned lock.

    Returns:

        True
            The lock is absent and acquisition can be retried.

        False
            The lock must remain untouched.

    Important:

    A malformed, empty, or temporarily unreadable lock is NEVER
    deleted merely because it is old.

    We can safely recover only when the lock contains a valid PID
    and that PID is definitely no longer running.
    """
    try:
        if not lock_path.exists():
            return True

    except OSError:
        return False

    owner = _read_lock_owner(
        lock_path,
    )

    if owner is None:
        # We cannot prove who owns this lock.
        #
        # This is deliberately treated as contention rather than
        # as an abandoned lock. Deleting an unknown lock could
        # allow two independent processes into the critical
        # section simultaneously.
        return False

    pid, _token = owner

    # Only a definitively dead owner is recoverable.
    if not is_pid_running(pid):
        return _remove_lock(
            lock_path,
        )

    # Live owner: NEVER steal.
    return False


def _try_acquire(
    lock_path: Path,
    pid: int,
    token: str,
) -> bool:
    """
    Atomically acquire the lock.

    O_CREAT | O_EXCL guarantees that only one independent
    process can create the lock file.
    """
    flags = (
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
    )

    try:
        fd = os.open(
            str(lock_path),
            flags,
        )

    except FileExistsError:
        return False

    except OSError:
        # A transient filesystem condition is treated as
        # contention. The caller will retry until its timeout.
        return False

    try:
        payload = (
            f"{pid}:{token}"
        ).encode("ascii")

        os.write(
            fd,
            payload,
        )

    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass

        # If metadata writing fails after successful O_EXCL
        # creation, remove our newly-created lock.
        #
        # _remove_lock() now handles a transient Windows sharing
        # violation without changing the ownership semantics.
        _remove_lock(
            lock_path,
        )

        raise

    finally:
        try:
            os.close(fd)
        except OSError:
            pass

    return True


def _owns_lock(
    lock_path: Path,
    pid: int,
    token: str,
) -> bool:
    """
    Return True only when the lock currently belongs to this
    exact acquisition.
    """
    owner = _read_lock_owner(
        lock_path,
    )

    if owner is None:
        return False

    owner_pid, owner_token = owner

    return (
        owner_pid == pid
        and owner_token == token
    )


@contextmanager
def file_lock(
    lock_path: Path,
    timeout: float = DEFAULT_TIMEOUT,
    delay: float = DEFAULT_DELAY,
) -> Iterator[None]:
    """
    Cross-process filesystem lock.

    Guarantees:

    - atomic acquisition via O_CREAT | O_EXCL
    - independent OS-process safety
    - bounded acquisition timeout
    - dead-process recovery when the owner PID is known
    - never steals a lock from a live process
    - never deletes an unknown/malformed lock
    - ownership-safe cleanup using PID + unique token
    - cleanup after normal exit
    - cleanup after exceptions
    """
    lock_path = Path(
        lock_path,
    )

    lock_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if timeout < 0:
        raise ValueError(
            "timeout must be >= 0"
        )

    if delay <= 0:
        delay = DEFAULT_DELAY

    pid = os.getpid()
    token = uuid.uuid4().hex

    deadline = (
        time.monotonic()
        + timeout
    )

    while True:
        # Fast path: attempt atomic creation immediately.
        if _try_acquire(
            lock_path,
            pid,
            token,
        ):
            break

        # We failed because another process currently has the
        # lock, or because the filesystem reported a transient
        # condition.
        #
        # Try recovery only when there is enough information to
        # prove the existing owner is dead.
        if _try_remove_stale_lock(
            lock_path,
        ):
            continue

        remaining = (
            deadline
            - time.monotonic()
        )

        if remaining <= 0:
            raise TimeoutError(
                f"Timed out waiting for file lock: "
                f"{lock_path}"
            )

        time.sleep(
            min(
                delay,
                remaining,
            )
        )

    try:
        yield

    finally:
        # Cleanup must only remove THIS acquisition.
        #
        # If another process has already replaced the lock,
        # ownership verification prevents us from deleting it.
        try:
            if _owns_lock(
                lock_path,
                pid,
                token,
            ):
                _remove_lock(
                    lock_path,
                )

        except Exception:
            # Never hide the application's original exception.
            pass