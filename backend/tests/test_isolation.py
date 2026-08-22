import os
os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.models import Cart, Order
from app.db.database import SessionLocal, init_db

client = TestClient(app)


def test_customer_isolation_and_missing_id():
    init_db()
    db_session = SessionLocal()
    try:
        # Create test data for Customer A
        cart_a = Cart(
            id="cart_cust_a",
            merchant_id="m_urbanrun",
            customer_id="cust_a",
            currency="INR",
            status="checked_out",
            subtotal_inr=1000,
            discount_inr=0,
            shipping_inr=0,
            total_inr=1000,
        )
        db_session.add(cart_a)
        db_session.commit()

        order_a = Order(
            order_id="ord_cust_a",
            cart_id="cart_cust_a",
            customer_id="cust_a",
            merchant_id="m_urbanrun",
            currency="INR",
            subtotal=1000,
            total=1000,
            status="placed",
        )
        db_session.add(order_a)
        db_session.commit()

        # 1. Test GET /order/{order_id} isolation
        # Missing customer_id query parameter
        res = client.get("/api/v1/checkout/order/ord_cust_a")
        assert res.status_code == 422  # Missing query param validation

        # Mismatched customer_id (Customer B)
        res = client.get("/api/v1/checkout/order/ord_cust_a?customer_id=cust_b")
        assert res.status_code == 403
        assert "Access denied" in res.json()["detail"]

        # Correct customer_id (Customer A)
        res = client.get("/api/v1/checkout/order/ord_cust_a?customer_id=cust_a")
        assert res.status_code == 200

        # 2. Test GET /order/by-cart/{cart_id} isolation
        # Missing customer_id
        res = client.get("/api/v1/checkout/order/by-cart/cart_cust_a")
        assert res.status_code == 422

        # Mismatched customer_id
        res = client.get("/api/v1/checkout/order/by-cart/cart_cust_a?customer_id=cust_b")
        assert res.status_code == 403

        # Correct customer_id
        res = client.get("/api/v1/checkout/order/by-cart/cart_cust_a?customer_id=cust_a")
        assert res.status_code == 200

        # 3. Test GET /order/{order_id}/tracking isolation
        # Missing customer_id
        res = client.get("/api/v1/checkout/order/ord_cust_a/tracking")
        assert res.status_code == 422

        # Mismatched customer_id
        res = client.get("/api/v1/checkout/order/ord_cust_a/tracking?customer_id=cust_b")
        assert res.status_code == 403

        # Correct customer_id
        res = client.get("/api/v1/checkout/order/ord_cust_a/tracking?customer_id=cust_a")
        assert res.status_code == 200

        # 4. Test POST /order/{order_id}/cancel isolation
        # Missing customer_id in CancelOrderRequest
        res = client.post("/api/v1/checkout/order/ord_cust_a/cancel", json={})
        assert res.status_code == 422

        # Mismatched customer_id in CancelOrderRequest
        res = client.post("/api/v1/checkout/order/ord_cust_a/cancel", json={"customer_id": "cust_b"})
        assert res.status_code == 403

        # Correct customer_id
        res = client.post("/api/v1/checkout/order/ord_cust_a/cancel", json={"customer_id": "cust_a"})
        assert res.status_code == 200

        # 5. Test POST /order/{order_id}/return isolation
        # Set status to delivered first for return eligibility
        order_a.status = "delivered"
        db_session.commit()

        # Missing customer_id in ReturnRequestInput
        res = client.post("/api/v1/checkout/order/ord_cust_a/return", json={"product_id": "ur_shoe_001"})
        assert res.status_code == 422

        # Mismatched customer_id
        res = client.post(
            "/api/v1/checkout/order/ord_cust_a/return",
            json={"product_id": "ur_shoe_001", "customer_id": "cust_b", "quantity": 1}
        )
        assert res.status_code == 403
    finally:
        db_session.close()
