import os
os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.catalog_service import _load_products
from app.db.database import SessionLocal
from app.db.models import Order

client = TestClient(app)


def test_generalization_search_products() -> None:
    # Search headphones under 5000
    res = client.get("/api/v1/catalog/products?query=headphones&max_price=5000")
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) > 0
    for product in data["items"]:
        assert product["category"] == "headphones"
        assert product["price"]["amount"] <= 5000

    # Search laptops
    res = client.get("/api/v1/catalog/products?query=laptops")
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) > 0
    categories = [p["category"] for p in data["items"]]
    assert "laptops" in categories


def test_generalization_compare_products() -> None:
    # Compare SoundWave ANC and EchoBuds Pro
    res = client.post("/api/v1/catalog/products/compare", json=["ur_audio_001", "ur_audio_002"])
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 2
    names = {p["name"] for p in data["items"]}
    assert "SoundWave ANC Wireless Headphones" in names
    assert "EchoBuds Pro True Wireless" in names


def test_generalization_mixed_cart_and_checkout() -> None:
    # 1. Create a cart
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_general_001"
    })
    assert create_res.status_code == 201
    cart_id = create_res.json()["cart_id"]

    # 2. Add SoundWave Headphones (ur_audio_001, price: 4499)
    add1 = client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_audio_001",
        "quantity": 1
    })
    assert add1.status_code == 200

    # 3. Add TrailPack Backpack (ur_gear_001, price: 2499)
    add2 = client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_gear_001",
        "quantity": 1
    })
    assert add2.status_code == 200

    # 4. Get cart and check items
    cart_res = client.get(f"/api/v1/cart/{cart_id}")
    assert cart_res.status_code == 200
    cart_data = cart_res.json()
    assert len(cart_data["items"]) == 2
    
    product_ids = {item["product_id"] for item in cart_data["items"]}
    assert "ur_audio_001" in product_ids
    assert "ur_gear_001" in product_ids
    
    # Subtotal: 4499 + 2499 = 6998
    assert cart_data["subtotal_inr"] == 6998

    # 5. Check initial inventory in catalog for ur_audio_001 and ur_gear_001
    products_before = _load_products()
    inv_audio_before = products_before["ur_audio_001"].inventory_quantity
    inv_gear_before = products_before["ur_gear_001"].inventory_quantity

    # 6. Proceed to Checkout
    checkout_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
        "payment_method": "mock_card",
        "customer_id": "c_general_001"
    })
    assert checkout_res.status_code == 200
    order_data = checkout_res.json()
    assert order_data["status"] == "placed"
    assert order_data["total"] == 6998
    assert len(order_data["items"]) == 2

    # 7. Check inventory was decremented correctly by 1
    products_after = _load_products()
    assert products_after["ur_audio_001"].inventory_quantity == inv_audio_before - 1
    assert products_after["ur_gear_001"].inventory_quantity == inv_gear_before - 1

    # 8. Check DB order creation
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.order_id == order_data["order_id"]).first()
        assert order is not None
        assert len(order.items) == 2
        assert order.total == 6998
        assert order.customer_id == "c_general_001"
    finally:
        db.close()

    # 9. Test Idempotency (duplicate checkout protection)
    dup_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
        "payment_method": "mock_card",
        "customer_id": "c_general_001"
    })
    assert dup_res.status_code == 200
    assert dup_res.json()["order_id"] == order_data["order_id"]
    
    # Inventory should remain decremented by exactly 1, not 2
    products_dup = _load_products()
    assert products_dup["ur_audio_001"].inventory_quantity == inv_audio_before - 1


def test_generalization_get_order_by_id_and_cart() -> None:
    # 1. Place order
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_general_002"
    })
    cart_id = create_res.json()["cart_id"]

    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_fit_001",  # Yoga Mat, price: 1999
        "quantity": 1
    })

    checkout_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
        "payment_method": "mock_upi",
        "customer_id": "c_general_002"
    })
    order_data = checkout_res.json()
    order_id = order_data["order_id"]

    # 2. Get order by ID
    get_res = client.get(f"/api/v1/checkout/order/{order_id}?customer_id=c_general_002")
    assert get_res.status_code == 200
    assert get_res.json()["cart_id"] == cart_id
    assert get_res.json()["items"][0]["product_id"] == "ur_fit_001"

    # 3. Get order by cart ID
    by_cart_res = client.get(f"/api/v1/checkout/order/by-cart/{cart_id}?customer_id=c_general_002")
    assert by_cart_res.status_code == 200
    assert by_cart_res.json()["order_id"] == order_id
