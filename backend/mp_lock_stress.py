from __future__ import annotations

import multiprocessing as mp
import os
import time
from pathlib import Path

from app.services.file_lock import file_lock


TEMP_DIR = Path("C:/Users/Amay/AppData/Local/Temp")

LOCK_FILE = (
    Path(os.environ["AGENTPAY_LOCK_FILE"])
    if os.environ.get("AGENTPAY_LOCK_FILE")
    else TEMP_DIR / "agentpay_mp_lock_test.lock"
)
RESULT_DIR = TEMP_DIR / "agentpay_mp_lock_results"

NUM_WORKERS = 4
LOCK_TIMEOUT = 3.0
HOLD_TIME = 0.10


def worker(
    worker_id: int,
    start_event,
) -> None:
    from app.services.file_lock import file_lock

    pid = os.getpid()
    started = time.monotonic()

    result_file = RESULT_DIR / f"worker_{worker_id}.txt"

    def log(message: str) -> None:
        elapsed = time.monotonic() - started

        print(
            f"worker={worker_id} "
            f"pid={pid} "
            f"t={elapsed:.3f}s "
            f"{message}",
            flush=True,
        )

    try:
        log("STARTED")

        log("WAITING_FOR_START")

        start_event.wait()

        log("START_SIGNAL_RECEIVED")

        log(
            f"BEFORE_LOCK "
            f"exists={LOCK_FILE.exists()}"
        )

        lock_started = time.monotonic()

        try:
            with file_lock(
                LOCK_FILE,
                timeout=LOCK_TIMEOUT,
                delay=0.01,
            ):
                acquired_after = (
                    time.monotonic()
                    - lock_started
                )

                log(
                    f"ACQUIRED "
                    f"wait={acquired_after:.3f}s"
                )

                log(
                    f"INSIDE_LOCK "
                    f"exists={LOCK_FILE.exists()}"
                )

                time.sleep(HOLD_TIME)

                log("ABOUT_TO_RELEASE")

        except TimeoutError as exc:
            total = time.monotonic() - started

            log(
                f"LOCK_TIMEOUT "
                f"total={total:.3f}s "
                f"error={exc}"
            )

            result_file.write_text(
                (
                    f"worker={worker_id}\n"
                    f"pid={pid}\n"
                    f"status=TIMEOUT\n"
                    f"total={total:.3f}\n"
                    f"error={type(exc).__name__}: {exc}\n"
                ),
                encoding="utf-8",
            )

            return

        total = time.monotonic() - started

        log(
            f"RELEASED "
            f"total={total:.3f}s"
        )

        result_file.write_text(
            (
                f"worker={worker_id}\n"
                f"pid={pid}\n"
                f"status=SUCCESS\n"
                f"acquired_after={acquired_after:.3f}\n"
                f"total={total:.3f}\n"
            ),
            encoding="utf-8",
        )

    except BaseException as exc:
        total = time.monotonic() - started

        log(
            f"CRASHED "
            f"{type(exc).__name__}: {exc}"
        )

        try:
            result_file.write_text(
                (
                    f"worker={worker_id}\n"
                    f"pid={pid}\n"
                    f"status=CRASHED\n"
                    f"error={type(exc).__name__}: {exc}\n"
                    f"total={total:.3f}\n"
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

        raise


def main() -> int:
    LOCK_FILE.unlink(missing_ok=True)

    if RESULT_DIR.exists():
        for path in RESULT_DIR.glob("worker_*.txt"):
            path.unlink(missing_ok=True)
    else:
        RESULT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

    print(f"parent pid={os.getpid()}")
    print(f"lock={LOCK_FILE}")
    print(f"result dir={RESULT_DIR}")
    print(f"workers={NUM_WORKERS}")
    print(f"lock timeout={LOCK_TIMEOUT}s")
    print(f"hold time={HOLD_TIME}s")
    print()

    ctx = mp.get_context("spawn")

    start_event = ctx.Event()

    processes: list[mp.Process] = []

    for worker_id in range(NUM_WORKERS):
        process = ctx.Process(
            target=worker,
            args=(
                worker_id,
                start_event,
            ),
            name=f"lock-worker-{worker_id}",
        )

        process.start()
        processes.append(process)

    print("all workers spawned")

    time.sleep(0.5)

    print("releasing start event")

    start_event.set()

    # Give enough time for:
    #
    #   4 workers
    #   × 0.1s critical section
    #   + lock timeout
    #   + process overhead
    #
    deadline = time.monotonic() + (
        LOCK_TIMEOUT
        + (HOLD_TIME * NUM_WORKERS)
        + 5.0
    )

    for process in processes:
        remaining = deadline - time.monotonic()

        if remaining <= 0:
            break

        process.join(
            timeout=remaining,
        )

    alive = [
        process
        for process in processes
        if process.is_alive()
    ]

    if alive:
        print()
        print("FAIL: workers did not finish:")

        for process in alive:
            print(
                f"  {process.name} "
                f"pid={process.pid}"
            )

        for process in alive:
            process.terminate()

        for process in alive:
            process.join(timeout=1)

    print()
    print("worker result files:")

    results = []

    for worker_id in range(NUM_WORKERS):
        result_file = RESULT_DIR / f"worker_{worker_id}.txt"

        if not result_file.exists():
            print(
                f"  worker={worker_id}: MISSING"
            )
            continue

        text = result_file.read_text(
            encoding="utf-8"
        ).strip()

        print(
            f"  worker={worker_id}:"
        )

        for line in text.splitlines():
            print(f"    {line}")

        results.append(text)

    print()
    print("exit codes:")

    for process in processes:
        print(
            f"  {process.name}: "
            f"exitcode={process.exitcode}"
        )

    print()
    print(
        f"lock exists: "
        f"{LOCK_FILE.exists()}"
    )

    success_count = sum(
        "status=SUCCESS" in result
        for result in results
    )

    if (
        len(results) != NUM_WORKERS
        or success_count != NUM_WORKERS
        or alive
        or any(
            process.exitcode != 0
            for process in processes
        )
        or LOCK_FILE.exists()
    ):
        print("RESULT: FAIL")
        return 1

    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())