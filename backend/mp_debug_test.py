import os
os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

import time


def _multiprocess_worker(product_id: str):
    os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"
    from app.services.catalog_service import decrement_inventory
    try:
        decrement_inventory({product_id: 1})
        return ("SUCCESS", None)
    except Exception as exc:
        return ("FAILED", str(exc))


if __name__ == "__main__":
    print("Parent PID:", os.getpid())
    print("Importing app.services.catalog_service in parent...")
    t0 = time.time()
    from app.services.catalog_service import (
        _load_products,
        _load_json,
        _safe_write_json,
        file_lock,
        LOCK_FILE,
    )
    print(f"Parent import took {time.time() - t0:.2f}s")

    product_id = "ur_shoe_001"
    products = _load_products()
    original_qty = products[product_id].inventory_quantity
    print("Original qty:", original_qty)

    with file_lock(LOCK_FILE):
        raw_products = _load_json("products.json")
        for p in raw_products:
            if p["id"] == product_id:
                p["inventory_quantity"] = 1
                p["available"] = True
        _safe_write_json("products.json", raw_products)
        _load_products.cache_clear()

    print("Set stock to 1. Starting ProcessPoolExecutor with 4 workers...")
    t1 = time.time()

    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_multiprocess_worker, product_id) for _ in range(4)]
        results = [f.result(timeout=30) for f in futures]

    print(f"Pool finished in {time.time() - t1:.2f}s")
    print("Results:", results)

    # restore
    with file_lock(LOCK_FILE):
        raw_products = _load_json("products.json")
        for p in raw_products:
            if p["id"] == product_id:
                p["inventory_quantity"] = original_qty
                p["available"] = True
        _safe_write_json("products.json", raw_products)
        _load_products.cache_clear()
    print("Restored original qty:", original_qty)
