import os
os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

import time
import pytest
from concurrent.futures import ThreadPoolExecutor
from app.services.catalog_service import (
    decrement_inventory,
    increment_inventory,
    _load_products,
    _load_json,
    _safe_write_json,
    file_lock,
    LOCK_FILE,
)

def test_inventory_decrement_success():
    products = _load_products()
    product_id = "ur_shoe_001"
    initial_qty = products[product_id].inventory_quantity
    
    # Decrement by 1
    decrement_inventory({product_id: 1})
    
    # Reload and check
    products = _load_products()
    assert products[product_id].inventory_quantity == initial_qty - 1
    
    # Restore
    increment_inventory({product_id: 1})

def test_inventory_decrement_insufficient():
    product_id = "ur_shoe_001"
    products = _load_products()
    current_qty = products[product_id].inventory_quantity
    
    # Try to decrement by more than current quantity
    with pytest.raises(ValueError, match="Insufficient inventory"):
        decrement_inventory({product_id: current_qty + 1})
        
    # Check that quantity is unchanged
    products = _load_products()
    assert products[product_id].inventory_quantity == current_qty

def test_inventory_increment_restores():
    product_id = "ur_shoe_001"
    products = _load_products()
    initial_qty = products[product_id].inventory_quantity
    
    increment_inventory({product_id: 5})
    products = _load_products()
    assert products[product_id].inventory_quantity == initial_qty + 5
    
    # Restore
    decrement_inventory({product_id: 5})

def test_concurrent_mutations_no_lost_updates():
    product_id = "ur_shoe_001"
    products = _load_products()
    initial_qty = products[product_id].inventory_quantity
    
    num_threads = 10
    
    # Ensure we have enough stock initially
    if initial_qty < num_threads:
        increment_inventory({product_id: num_threads - initial_qty})
        initial_qty = num_threads

    def worker(_):
        try:
            decrement_inventory({product_id: 1})
            return True
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        results = list(executor.map(worker, range(num_threads)))
        
    success_count = sum(1 for r in results if r)
    assert success_count == num_threads
    
    # Verify final quantity is exactly initial_qty - num_threads
    products = _load_products()
    assert products[product_id].inventory_quantity == initial_qty - num_threads
    
    # Restore original quantity
    increment_inventory({product_id: num_threads})


def test_competing_decrement_single_stock():
    """
    Given a product with exactly stock=1, two competing decrement operations run concurrently.
    Exactly ONE must succeed, exactly ONE must fail with ValueError, final stock must be 0 (never negative).
    """
    product_id = "ur_shoe_001"
    products = _load_products()
    original_qty = products[product_id].inventory_quantity

    # Temporarily set stock to exactly 1
    with file_lock(LOCK_FILE):
        raw_products = _load_json("products.json")
        for p in raw_products:
            if p["id"] == product_id:
                p["inventory_quantity"] = 1
                p["available"] = True
        _safe_write_json("products.json", raw_products)
        _load_products.cache_clear()

    results = []

    def attempt_purchase(_):
        try:
            decrement_inventory({product_id: 1})
            return ("SUCCESS", None)
        except Exception as exc:
            return ("FAILED", str(exc))

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(attempt_purchase, i) for i in range(2)]
        results = [f.result() for f in futures]

    successes = [r for r in results if r[0] == "SUCCESS"]
    failures = [r for r in results if r[0] == "FAILED"]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}: {results}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}: {results}"
    assert "Insufficient inventory" in failures[0][1]

    # Verify final stock is 0 and available is False
    products = _load_products()
    assert products[product_id].inventory_quantity == 0
    assert products[product_id].available is False

    # Restore original quantity
    with file_lock(LOCK_FILE):
        raw_products = _load_json("products.json")
        for p in raw_products:
            if p["id"] == product_id:
                p["inventory_quantity"] = original_qty
                p["available"] = True
        _safe_write_json("products.json", raw_products)
        _load_products.cache_clear()


def test_stale_lock_recovery_and_cleanup():
    """
    Verifies that a stale lock file (>3 seconds old) is evicted cleanly
    and that exception inside file_lock block releases the lock in finally block.
    """
    from app.services.catalog_service import LOCK_FILE, file_lock
    import time

    # 1. Test exception cleanup in finally block
    try:
        with file_lock(LOCK_FILE):
            raise RuntimeError("Simulated failure inside locked region")
    except RuntimeError:
        pass

    assert not LOCK_FILE.exists(), "Lock file was left behind after exception!"

    # 2. Test stale lock file recovery (> 3 seconds old)
    LOCK_FILE.write_text("999999", encoding="utf-8")
    # Backdate mtime by 5 seconds
    past_time = time.time() - 5.0
    os.utime(LOCK_FILE, (past_time, past_time))

    # file_lock must evict stale lock and acquire successfully
    acquired = False
    with file_lock(LOCK_FILE, timeout=2.0):
        acquired = True

    assert acquired, "Failed to acquire lock after stale lock eviction!"
    assert not LOCK_FILE.exists(), "Lock file was left behind after exit!"

