import os
os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.models import Cart, Order, OrderItem, ReturnRequest, ReturnItem
from app.db.database import SessionLocal, init_db
from app.services.auth_service import create_session_token

client = TestClient(app)


def test_customer_isolation_and_missing_id():
    init_db()
    db_session = SessionLocal()
    try:
        # Clean up existing test records if any to prevent UNIQUE constraint errors
        db_session.query(ReturnItem).delete()
        db_session.query(ReturnRequest).delete()
        db_session.query(OrderItem).filter(OrderItem.order_id.in_(["ord_cust_a", "ord_cust_a_deliv"])).delete()
        db_session.query(Order).filter(Order.order_id.in_(["ord_cust_a", "ord_cust_a_deliv"])).delete()
        db_session.query(Cart).filter(Cart.id.in_(["cart_cust_a", "cart_cust_a_deliv"])).delete()
        db_session.commit()

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
        item_a = OrderItem(
            order_id="ord_cust_a",
            product_id="ur_shoe_001",
            sku="UR-RS-001",
            name="AeroRun X1",
            unit_price=1000,
            quantity=1,
            line_total=1000,
        )
        order_a.items.append(item_a)
        db_session.add(order_a)
        db_session.commit()

        headers_a = {"Authorization": f"Bearer {create_session_token('cust_a')}"}
        headers_b = {"Authorization": f"Bearer {create_session_token('cust_b')}"}

        # 1. Test GET /order/{order_id} isolation
        # Missing token
        res = client.get("/api/v1/checkout/order/ord_cust_a")
        assert res.status_code == 401

        # Customer B token accessing Customer A order
        res = client.get("/api/v1/checkout/order/ord_cust_a", headers=headers_b)
        assert res.status_code == 403
        assert "Access denied" in res.json()["detail"]

        # Correct customer token (Customer A)
        res = client.get("/api/v1/checkout/order/ord_cust_a", headers=headers_a)
        assert res.status_code == 200

        # 2. Test GET /order/by-cart/{cart_id} isolation
        # Missing token
        res = client.get("/api/v1/checkout/order/by-cart/cart_cust_a")
        assert res.status_code == 401

        # Mismatched customer token
        res = client.get("/api/v1/checkout/order/by-cart/cart_cust_a", headers=headers_b)
        assert res.status_code == 403

        # Correct customer token
        res = client.get("/api/v1/checkout/order/by-cart/cart_cust_a", headers=headers_a)
        assert res.status_code == 200

        # 3. Test GET /order/{order_id}/tracking isolation
        # Missing token
        res = client.get("/api/v1/checkout/order/ord_cust_a/tracking")
        assert res.status_code == 401

        # Mismatched customer token
        res = client.get("/api/v1/checkout/order/ord_cust_a/tracking", headers=headers_b)
        assert res.status_code == 403

        # Correct customer token
        res = client.get("/api/v1/checkout/order/ord_cust_a/tracking", headers=headers_a)
        assert res.status_code == 200

        # 4. Test POST /order/{order_id}/cancel isolation
        # Missing token
        res = client.post("/api/v1/checkout/order/ord_cust_a/cancel", json={})
        assert res.status_code == 401

        # Mismatched customer token
        res = client.post("/api/v1/checkout/order/ord_cust_a/cancel", json={}, headers=headers_b)
        assert res.status_code == 403

        # Correct customer token
        res = client.post("/api/v1/checkout/order/ord_cust_a/cancel", json={}, headers=headers_a)
        assert res.status_code == 200

        # 5. Test POST /order/{order_id}/return isolation
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        db_session.query(OrderItem).filter(OrderItem.order_id == "ord_cust_a_deliv").delete()
        db_session.query(Order).filter(Order.order_id == "ord_cust_a_deliv").delete()
        db_session.commit()

        order_deliv = Order(
            order_id="ord_cust_a_deliv",
            cart_id="cart_cust_a_deliv",
            customer_id="cust_a",
            merchant_id="m_urbanrun",
            currency="INR",
            subtotal=1000,
            total=1000,
            status="delivered",
            created_at=now,
            delivered_at=now,
        )
        item_deliv = OrderItem(
            order_id="ord_cust_a_deliv",
            product_id="ur_shoe_001",
            sku="UR-RS-001",
            name="AeroRun X1",
            unit_price=1000,
            quantity=1,
            line_total=1000,
        )
        order_deliv.items.append(item_deliv)
        db_session.add(order_deliv)
        db_session.commit()

        # Missing token
        res = client.post("/api/v1/checkout/order/ord_cust_a_deliv/return", json={"product_id": "ur_shoe_001"})
        assert res.status_code == 401

        # Mismatched customer token
        res = client.post(
            "/api/v1/checkout/order/ord_cust_a_deliv/return",
            json={"product_id": "ur_shoe_001", "quantity": 1},
            headers=headers_b,
        )
        assert res.status_code == 403

        # Correct customer token
        res = client.post(
            "/api/v1/checkout/order/ord_cust_a_deliv/return",
            json={"product_id": "ur_shoe_001", "quantity": 1},
            headers=headers_a,
        )
        assert res.status_code == 200
    finally:
        db_session.close()
