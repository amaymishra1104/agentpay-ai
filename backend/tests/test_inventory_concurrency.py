import os
os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

import time
import pytest
from concurrent.futures import ThreadPoolExecutor
from app.services.catalog_service import (
    decrement_inventory,
    increment_inventory,
    _load_products,
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
