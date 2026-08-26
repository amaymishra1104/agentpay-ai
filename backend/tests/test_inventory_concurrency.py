import multiprocessing as mp
import os
import time

os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

import pytest
from concurrent.futures import ThreadPoolExecutor

from app.services.catalog_service import (
    LOCK_FILE,
    _load_json,
    _load_products,
    _safe_write_json,
    decrement_inventory,
    file_lock,
    increment_inventory,
)
from app.services.file_lock import is_pid_running


PRODUCT_ID = "ur_shoe_001"


def _set_product_inventory(
    product_id: str,
    quantity: int,
    available: bool | None = None,
):
    """
    Test helper that updates a product's inventory while holding the
    same production lock used by catalog_service.
    """
    with file_lock(LOCK_FILE):
        raw_products = _load_json("products.json")

        found = False

        for product in raw_products:
            if product["id"] == product_id:
                product["inventory_quantity"] = quantity

                if available is not None:
                    product["available"] = available

                found = True
                break

        if not found:
            raise AssertionError(
                f"Product {product_id} not found"
            )

        _safe_write_json(
            "products.json",
            raw_products,
        )

        _load_products.cache_clear()


def _multiprocess_inventory_worker(
    product_id: str,
    result_queue,
):
    """
    Worker used by the real OS-process concurrency test.
    """
    try:
        decrement_inventory(
            {
                product_id: 1
            }
        )

        result_queue.put(
            (
                os.getpid(),
                "SUCCESS",
                None,
            )
        )

    except Exception as exc:
        result_queue.put(
            (
                os.getpid(),
                "FAILED",
                f"{type(exc).__name__}: {exc}",
            )
        )


def _pid_liveness_worker(
    lock_path,
    ready_queue,
    release_event,
    result_queue,
):
    """
    Worker used by the Windows PID-liveness regression test.
    """
    try:
        with file_lock(
            lock_path,
            timeout=5.0,
            delay=0.01,
        ):
            ready_queue.put(
                os.getpid()
            )

            release_event.wait(
                timeout=10.0
            )

            result_queue.put(
                (
                    os.getpid(),
                    "COMPLETED",
                    None,
                )
            )

    except Exception as exc:
        result_queue.put(
            (
                os.getpid(),
                "FAILED",
                f"{type(exc).__name__}: {exc}",
            )
        )


def _cleanup_processes(processes):
    """
    Make sure no child process survives a failed test.
    """
    for process in processes:
        if process.is_alive():
            process.terminate()

    for process in processes:
        process.join(
            timeout=5
        )


def _rapid_lock_worker(
    lock_path,
    worker_id,
    iterations,
    result_queue,
):
    """
    Rapid same-process-style lock stress worker.

    Each worker runs many short acquire/release cycles against the
    same lock path.

    This is deliberately aggressive because the Bug #2 failure was
    a narrow Windows delete/read/open sharing-violation race.
    """
    try:
        for iteration in range(
            iterations
        ):
            with file_lock(
                lock_path,
                timeout=5.0,
                delay=0.001,
            ):
                # Keep the critical section extremely short.
                pass

        result_queue.put(
            (
                worker_id,
                "SUCCESS",
                iterations,
                None,
            )
        )

    except Exception as exc:
        result_queue.put(
            (
                worker_id,
                "FAILED",
                0,
                f"{type(exc).__name__}: {exc}",
            )
        )


def test_inventory_decrement_success():
    products = _load_products()

    initial_qty = (
        products[PRODUCT_ID]
        .inventory_quantity
    )

    decrement_inventory(
        {
            PRODUCT_ID: 1
        }
    )

    products = _load_products()

    assert (
        products[PRODUCT_ID].inventory_quantity
        == initial_qty - 1
    )

    increment_inventory(
        {
            PRODUCT_ID: 1
        }
    )


def test_inventory_decrement_insufficient():
    products = _load_products()

    current_qty = (
        products[PRODUCT_ID]
        .inventory_quantity
    )

    with pytest.raises(
        ValueError,
        match="Insufficient inventory",
    ):
        decrement_inventory(
            {
                PRODUCT_ID: current_qty + 1
            }
        )

    products = _load_products()

    assert (
        products[PRODUCT_ID].inventory_quantity
        == current_qty
    )


def test_inventory_increment_restores():
    products = _load_products()

    initial_qty = (
        products[PRODUCT_ID]
        .inventory_quantity
    )

    increment_inventory(
        {
            PRODUCT_ID: 5
        }
    )

    products = _load_products()

    assert (
        products[PRODUCT_ID].inventory_quantity
        == initial_qty + 5
    )

    decrement_inventory(
        {
            PRODUCT_ID: 5
        }
    )


def test_concurrent_mutations_no_lost_updates():
    """
    Ten threads each decrement one unit.

    Expected:
        10 successful decrements
        final stock = initial stock - 10
    """
    products = _load_products()

    initial_qty = (
        products[PRODUCT_ID]
        .inventory_quantity
    )

    num_threads = 10

    if initial_qty < num_threads:
        increment_inventory(
            {
                PRODUCT_ID: num_threads - initial_qty
            }
        )

        initial_qty = num_threads

    def worker(index):
        try:
            decrement_inventory(
                {
                    PRODUCT_ID: 1
                }
            )

            return (
                index,
                True,
                None,
            )

        except Exception as exc:
            return (
                index,
                False,
                f"{type(exc).__name__}: {exc}",
            )

    with ThreadPoolExecutor(
        max_workers=num_threads,
    ) as executor:
        results = list(
            executor.map(
                worker,
                range(num_threads),
            )
        )

    successes = [
        result
        for result in results
        if result[1] is True
    ]

    failures = [
        result
        for result in results
        if result[1] is False
    ]

    print("\nTHREAD CONCURRENCY RESULTS")

    for result in results:
        print(result)

    assert len(successes) == num_threads, (
        "Concurrent inventory operations failed.\n"
        f"Successes: {successes}\n"
        f"Failures: {failures}"
    )

    assert not LOCK_FILE.exists()

    products = _load_products()

    assert (
        products[PRODUCT_ID].inventory_quantity
        == initial_qty - num_threads
    )

    increment_inventory(
        {
            PRODUCT_ID: num_threads
        }
    )


def test_competing_decrement_single_stock():
    """
    Two threads compete for exactly one unit.

    Exactly one operation must succeed.
    Exactly one must fail with insufficient inventory.
    """
    products = _load_products()

    original_qty = (
        products[PRODUCT_ID]
        .inventory_quantity
    )

    original_available = (
        products[PRODUCT_ID]
        .available
    )

    try:
        _set_product_inventory(
            PRODUCT_ID,
            quantity=1,
            available=True,
        )

        def attempt_purchase(_):
            try:
                decrement_inventory(
                    {
                        PRODUCT_ID: 1
                    }
                )

                return (
                    "SUCCESS",
                    None,
                )

            except Exception as exc:
                return (
                    "FAILED",
                    str(exc),
                )

        with ThreadPoolExecutor(
            max_workers=2,
        ) as executor:
            results = list(
                executor.map(
                    attempt_purchase,
                    range(2),
                )
            )

        successes = [
            result
            for result in results
            if result[0] == "SUCCESS"
        ]

        failures = [
            result
            for result in results
            if result[0] == "FAILED"
        ]

        assert len(successes) == 1, (
            f"Expected exactly 1 success: {results}"
        )

        assert len(failures) == 1, (
            f"Expected exactly 1 failure: {results}"
        )

        assert (
            "Insufficient inventory"
            in failures[0][1]
        )

        products = _load_products()

        assert (
            products[PRODUCT_ID]
            .inventory_quantity
            == 0
        )

        assert (
            products[PRODUCT_ID]
            .available
            is False
        )

    finally:
        _set_product_inventory(
            PRODUCT_ID,
            quantity=original_qty,
            available=original_available,
        )


def test_rapid_same_process_lock_contention():
    """
    Regression test for the Windows same-process lock cleanup race.

    Many threads repeatedly acquire and release the same lock with
    virtually no hold time.

    The old implementation could leave an orphaned lock when
    _remove_lock() encountered a transient Windows ERROR_SHARING_VIOLATION.

    Expected:
        every worker completes every iteration
        no worker times out
        lock does not remain afterward
    """
    LOCK_FILE.unlink(
        missing_ok=True
    )

    num_workers = 10
    iterations_per_worker = 100

    ctx = mp.get_context("spawn")

    # The actual lock contention is created by ThreadPoolExecutor
    # below. The process-style queue is not required for correctness;
    # this helper gives us a simple worker/result structure.
    #
    # Use direct thread workers here so all workers share the same
    # process and therefore exercise the exact race discovered in Bug #2.
    results = []

    def worker(worker_id):
        completed = 0

        try:
            for _ in range(
                iterations_per_worker
            ):
                with file_lock(
                    LOCK_FILE,
                    timeout=15.0,
                    delay=0.001,
                ):
                    completed += 1

            return (
                worker_id,
                "SUCCESS",
                completed,
                None,
            )

        except Exception as exc:
            return (
                worker_id,
                "FAILED",
                completed,
                f"{type(exc).__name__}: {exc}",
            )

    try:
        with ThreadPoolExecutor(
            max_workers=num_workers,
        ) as executor:
            results = list(
                executor.map(
                    worker,
                    range(num_workers),
                )
            )

        print("\nRAPID SAME-PROCESS LOCK RESULTS")

        for result in results:
            print(result)

        failures = [
            result
            for result in results
            if result[1] != "SUCCESS"
        ]

        assert not failures, (
            "Rapid same-process lock stress failed.\n"
            f"Failures: {failures}"
        )

        assert all(
            result[2] == iterations_per_worker
            for result in results
        )

        assert not LOCK_FILE.exists()

    finally:
        LOCK_FILE.unlink(
            missing_ok=True
        )


def test_stale_lock_recovery_and_cleanup():
    """
    Verifies normal cleanup, exception cleanup, and dead-PID recovery.
    """
    LOCK_FILE.unlink(
        missing_ok=True
    )

    try:
        with file_lock(
            LOCK_FILE
        ):
            assert LOCK_FILE.exists()

            raise RuntimeError(
                "Simulated failure inside locked region"
            )

    except RuntimeError:
        pass

    assert not LOCK_FILE.exists()

    LOCK_FILE.write_text(
        "999999",
        encoding="utf-8",
    )

    acquired = False

    try:
        with file_lock(
            LOCK_FILE,
            timeout=2.0,
            delay=0.01,
        ):
            acquired = True

        assert acquired
        assert not LOCK_FILE.exists()

    finally:
        LOCK_FILE.unlink(
            missing_ok=True
        )


def test_multiprocess_competing_decrement_single_stock():
    """
    Four independent OS processes compete for exactly one unit.

    Expected:
        exactly 1 SUCCESS
        exactly 3 FAILED
        final inventory = 0
        no lock remains
    """
    products = _load_products()

    original_qty = (
        products[PRODUCT_ID]
        .inventory_quantity
    )

    original_available = (
        products[PRODUCT_ID]
        .available
    )

    processes = []

    try:
        _set_product_inventory(
            PRODUCT_ID,
            quantity=1,
            available=True,
        )

        _load_products.cache_clear()

        ctx = mp.get_context(
            "spawn"
        )

        result_queue = ctx.Queue()

        num_processes = 4

        for _ in range(num_processes):
            process = ctx.Process(
                target=_multiprocess_inventory_worker,
                args=(
                    PRODUCT_ID,
                    result_queue,
                ),
            )

            process.start()
            processes.append(process)

        results = []

        deadline = (
            time.monotonic()
            + 15.0
        )

        while len(results) < num_processes:
            remaining = (
                deadline
                - time.monotonic()
            )

            if remaining <= 0:
                break

            try:
                results.append(
                    result_queue.get(
                        timeout=min(
                            remaining,
                            1.0,
                        )
                    )
                )

            except Exception:
                continue

        if len(results) != num_processes:
            alive = [
                process.pid
                for process in processes
                if process.is_alive()
            ]

            pytest.fail(
                "Multiprocess inventory test timed out. "
                f"Received {len(results)}/{num_processes}. "
                f"Alive PIDs: {alive}"
            )

        for process in processes:
            process.join(
                timeout=5
            )

        still_alive = [
            process.pid
            for process in processes
            if process.is_alive()
        ]

        assert not still_alive, (
            f"Workers did not terminate: {still_alive}"
        )

        successes = [
            result
            for result in results
            if result[1] == "SUCCESS"
        ]

        failures = [
            result
            for result in results
            if result[1] == "FAILED"
        ]

        assert len(successes) == 1, (
            f"Expected 1 success: {results}"
        )

        assert len(failures) == 3, (
            f"Expected 3 failures: {results}"
        )

        assert all(
            "Insufficient inventory" in result[2]
            for result in failures
        )

        _load_products.cache_clear()

        products = _load_products()

        assert (
            products[PRODUCT_ID]
            .inventory_quantity
            == 0
        )

        assert (
            products[PRODUCT_ID]
            .available
            is False
        )

        assert not LOCK_FILE.exists()

    finally:
        _cleanup_processes(
            processes
        )

        try:
            _set_product_inventory(
                PRODUCT_ID,
                quantity=original_qty,
                available=original_available,
            )

        finally:
            LOCK_FILE.unlink(
                missing_ok=True
            )


def test_checkout_transaction_failure_rollback():
    """
    Simulates a database failure during checkout after inventory
    has already been decremented.

    Inventory must be restored.
    """
    from unittest.mock import patch

    from app.db.database import (
        SessionLocal,
        init_db,
    )
    from app.services import (
        cart_service,
        checkout_service,
    )

    init_db()

    product_id = PRODUCT_ID

    products_before = _load_products()

    initial_stock = (
        products_before[product_id]
        .inventory_quantity
    )

    with SessionLocal() as db:
        cart = cart_service.create_cart(
            merchant_id="m_urbanrun",
            customer_id="customer_roll_01",
            db=db,
        )

        cart_service.add_item_to_cart(
            cart.id,
            product_id,
            1,
            db,
            customer_id="customer_roll_01",
        )

        with patch.object(
            db,
            "commit",
            side_effect=RuntimeError(
                "Simulated DB commit crash"
            ),
        ):
            with pytest.raises(
                RuntimeError,
                match="Simulated DB commit crash",
            ):
                checkout_service.checkout_cart(
                    cart.id,
                    "mock_upi",
                    db,
                    customer_id="customer_roll_01",
                )

    products_after_fail = _load_products()

    assert (
        products_after_fail[product_id]
        .inventory_quantity
        == initial_stock
    )

    assert not LOCK_FILE.exists()

    with SessionLocal() as db:
        order = checkout_service.checkout_cart(
            cart.id,
            "mock_upi",
            db,
            customer_id="customer_roll_01",
        )

        assert order.order_id is not None
        assert order.status == "placed"

    products_final = _load_products()

    assert (
        products_final[product_id]
        .inventory_quantity
        == initial_stock - 1
    )

    increment_inventory(
        {
            product_id: 1
        }
    )


def test_dead_pid_lock_recovery_and_live_lock_respect():
    """
    Verifies:

    1. Dead PID locks can be recovered.
    2. Live PID locks cannot be stolen.
    """
    LOCK_FILE.unlink(
        missing_ok=True
    )

    LOCK_FILE.write_text(
        "999999",
        encoding="utf-8",
    )

    try:
        acquired_dead = False

        with file_lock(
            LOCK_FILE,
            timeout=2.0,
            delay=0.01,
        ):
            acquired_dead = True

        assert acquired_dead
        assert not LOCK_FILE.exists()

    finally:
        LOCK_FILE.unlink(
            missing_ok=True
        )

    LOCK_FILE.unlink(
        missing_ok=True
    )

    try:
        with file_lock(
            LOCK_FILE,
            timeout=1.0,
            delay=0.01,
        ):
            assert LOCK_FILE.exists()

            with pytest.raises(
                TimeoutError,
                match="Timed out waiting for file lock",
            ):
                with file_lock(
                    LOCK_FILE,
                    timeout=0.25,
                    delay=0.01,
                ):
                    pass

            assert LOCK_FILE.exists()

    finally:
        LOCK_FILE.unlink(
            missing_ok=True
        )

    assert not LOCK_FILE.exists()


def test_is_pid_running_does_not_terminate_live_process():
    """
    Regression test for the Windows os.kill(pid, 0) bug.

    A child process holds the real production lock while the parent
    checks its PID.

    The child must survive the liveness check and finish normally.
    """
    LOCK_FILE.unlink(
        missing_ok=True
    )

    ctx = mp.get_context(
        "spawn"
    )

    ready_queue = ctx.Queue()
    result_queue = ctx.Queue()
    release_event = ctx.Event()

    process = ctx.Process(
        target=_pid_liveness_worker,
        args=(
            LOCK_FILE,
            ready_queue,
            release_event,
            result_queue,
        ),
    )

    process.start()

    try:
        child_pid = ready_queue.get(
            timeout=10
        )

        assert child_pid == process.pid

        assert is_pid_running(
            child_pid
        ) is True

        assert process.is_alive()

        release_event.set()

        result = result_queue.get(
            timeout=10
        )

        assert result[0] == child_pid
        assert result[1] == "COMPLETED", result

        process.join(
            timeout=5
        )

        assert not process.is_alive()
        assert process.exitcode == 0
        assert not LOCK_FILE.exists()

    finally:
        release_event.set()

        if process.is_alive():
            process.terminate()

        process.join(
            timeout=5
        )

        LOCK_FILE.unlink(
            missing_ok=True
        )