import os
os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

import pytest
from fastapi.testclient import TestClient
from datetime import datetime

from app.main import app
from app.db.database import SessionLocal
from app.db.models import Order
from app.services.catalog_service import _load_products

class ClientWrapper:
    def __init__(self, client):
        self.client = client
        self.last_customer_id = "c_post_001"

    def get(self, url, *args, **kwargs):
        if "/api/v1/cart/" in url and "customer_id" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}customer_id={self.last_customer_id}"
        return self.client.get(url, *args, **kwargs)

    def post(self, url, *args, **kwargs):
        if url == "/api/v1/cart":
            json_data = kwargs.get("json", {})
            if json_data and "customer_id" in json_data:
                self.last_customer_id = json_data["customer_id"]
        if "/api/v1/cart/" in url and "customer_id" not in url and not url.endswith("/checkout"):
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}customer_id={self.last_customer_id}"
        return self.client.post(url, *args, **kwargs)

    def patch(self, url, *args, **kwargs):
        if "/api/v1/cart/" in url and "customer_id" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}customer_id={self.last_customer_id}"
        return self.client.patch(url, *args, **kwargs)

    def delete(self, url, *args, **kwargs):
        if "/api/v1/cart/" in url and "customer_id" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}customer_id={self.last_customer_id}"
        return self.client.delete(url, *args, **kwargs)

client = ClientWrapper(TestClient(app))


def test_post_purchase_lifecycle_and_tracking() -> None:
    # 1. Place order
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_post_001"
    })
    cart_id = create_res.json()["cart_id"]

    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_audio_001",
        "quantity": 2
    })

    checkout_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
        "payment_method": "mock_upi",
        "customer_id": "c_post_001"
    })
    assert checkout_res.status_code == 200
    order_data = checkout_res.json()
    order_id = order_data["order_id"]
    assert order_data["status"] == "placed"

    # 2. Get tracking timeline (placed state)
    track_res = client.get(f"/api/v1/checkout/order/{order_id}/tracking?customer_id=c_post_001")
    assert track_res.status_code == 200
    track_data = track_res.json()
    assert track_data["status"] == "placed"
    assert len(track_data["timeline"]) == 6
    assert track_data["timeline"][0]["completed"] is True
    assert track_data["timeline"][1]["completed"] is False  # Confirmed is pending

    # 3. Advance to Confirmed
    adv1 = client.post(f"/api/v1/checkout/order/{order_id}/advance-status")
    assert adv1.status_code == 200
    assert adv1.json()["status"] == "confirmed"

    # 4. Get tracking timeline (confirmed state)
    track_res = client.get(f"/api/v1/checkout/order/{order_id}/tracking?customer_id=c_post_001")
    track_data = track_res.json()
    assert track_data["timeline"][0]["completed"] is True
    assert track_data["timeline"][1]["completed"] is True   # Confirmed is complete
    assert track_data["timeline"][2]["completed"] is False  # Packed is pending

    # 5. Advance through to Shipped
    client.post(f"/api/v1/checkout/order/{order_id}/advance-status")  # packed
    adv3 = client.post(f"/api/v1/checkout/order/{order_id}/advance-status")  # shipped
    assert adv3.json()["status"] == "shipped"

    # 6. Try to cancel shipped order (should be rejected)
    cancel_res = client.post(f"/api/v1/checkout/order/{order_id}/cancel", json={
        "customer_id": "c_post_001"
    })
    assert cancel_res.status_code == 400
    assert "not eligible for cancellation" in cancel_res.json()["detail"].lower()


def test_post_purchase_cancellation_and_inventory_restore() -> None:
    # 1. Place order
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_post_002"
    })
    cart_id = create_res.json()["cart_id"]

    # Headphones (ur_audio_001)
    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_audio_001",
        "quantity": 1
    })

    products_before = _load_products()
    inv_before = products_before["ur_audio_001"].inventory_quantity

    checkout_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
        "payment_method": "mock_card",
        "customer_id": "c_post_002"
    })
    order_id = checkout_res.json()["order_id"]

    # Deducted inventory check
    products_after_checkout = _load_products()
    assert products_after_checkout["ur_audio_001"].inventory_quantity == inv_before - 1

    # 2. Cancel order
    cancel_res = client.post(f"/api/v1/checkout/order/{order_id}/cancel", json={
        "customer_id": "c_post_002"
    })
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"
    assert cancel_res.json()["payment_status"] == "refunded"

    # Restored inventory check
    products_after_cancel = _load_products()
    assert products_after_cancel["ur_audio_001"].inventory_quantity == inv_before

    # 3. Duplicate cancellation check (must be idempotent/ignored gracefully)
    cancel_res_dup = client.post(f"/api/v1/checkout/order/{order_id}/cancel", json={
        "customer_id": "c_post_002"
    })
    assert cancel_res_dup.status_code == 200
    assert cancel_res_dup.json()["status"] == "cancelled"
    
    # Must NOT restore inventory twice
    products_dup = _load_products()
    assert products_dup["ur_audio_001"].inventory_quantity == inv_before


def test_post_purchase_returns_workflow() -> None:
    # 1. Place and complete order
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_post_003"
    })
    cart_id = create_res.json()["cart_id"]

    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_audio_001",
        "quantity": 1
    })

    checkout_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
        "payment_method": "mock_card",
        "customer_id": "c_post_003"
    })
    order_id = checkout_res.json()["order_id"]

    # Try return in placed status (should fail)
    ret_fail = client.post(f"/api/v1/checkout/order/{order_id}/return", json={
        "customer_id": "c_post_003",
        "product_id": "ur_audio_001",
        "quantity": 1,
        "reason": "Not fits"
    })
    assert ret_fail.status_code == 400
    assert "eligible for return" in ret_fail.json()["detail"].lower()

    # Move order status all the way to delivered
    client.post(f"/api/v1/checkout/order/{order_id}/advance-status") # confirmed
    client.post(f"/api/v1/checkout/order/{order_id}/advance-status") # packed
    client.post(f"/api/v1/checkout/order/{order_id}/advance-status") # shipped
    client.post(f"/api/v1/checkout/order/{order_id}/advance-status") # out_for_delivery
    client.post(f"/api/v1/checkout/order/{order_id}/advance-status") # delivered

    # 2. Submit valid return request
    ret_success = client.post(f"/api/v1/checkout/order/{order_id}/return", json={
        "customer_id": "c_post_003",
        "product_id": "ur_audio_001",
        "quantity": 1,
        "reason": "Defective item received"
    })
    assert ret_success.status_code == 200
    ret_data = ret_success.json()
    assert ret_data["status"] == "requested"
    assert len(ret_data["items"]) == 1
    assert ret_data["items"][0]["product_id"] == "ur_audio_001"
    assert ret_data["items"][0]["reason"] == "Defective item received"

    # 3. Duplicate return request (should fail)
    ret_dup = client.post(f"/api/v1/checkout/order/{order_id}/return", json={
        "customer_id": "c_post_003",
        "product_id": "ur_audio_001",
        "quantity": 1,
        "reason": "Duplicate try"
    })
    assert ret_dup.status_code == 400
    assert "already been submitted" in ret_dup.json()["detail"].lower()


def test_post_purchase_security_ownership() -> None:
    # 1. Customer A places order
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_customer_a"
    })
    cart_id = create_res.json()["cart_id"]

    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_audio_001",
        "quantity": 1
    })

    checkout_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
        "payment_method": "mock_card",
        "customer_id": "c_customer_a"
    })
    order_id = checkout_res.json()["order_id"]

    # 2. Customer B attempts to track Customer A's order (should fail)
    track_res = client.get(f"/api/v1/checkout/order/{order_id}/tracking?customer_id=c_customer_b")
    assert track_res.status_code == 403
    assert "access denied" in track_res.json()["detail"].lower()

    # 3. Customer B attempts to cancel Customer A's order (should fail)
    cancel_res = client.post(f"/api/v1/checkout/order/{order_id}/cancel", json={
        "customer_id": "c_customer_b"
    })
    assert cancel_res.status_code == 403
    assert "access denied" in cancel_res.json()["detail"].lower()

    # 4. Customer B attempts to return Customer A's order (should fail)
    return_res = client.post(f"/api/v1/checkout/order/{order_id}/return", json={
        "customer_id": "c_customer_b",
        "product_id": "ur_audio_001",
        "quantity": 1
    })
    assert return_res.status_code == 403
    assert "access denied" in return_res.json()["detail"].lower()
