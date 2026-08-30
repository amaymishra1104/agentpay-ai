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
from app.agents.graph import build_buyer_graph
from app.agents.state import BuyerAgentState

class ClientWrapper:
    def __init__(self, client):
        self.client = client

    def get(self, url, *args, **kwargs):
        if "/api/v1/cart/" in url and "customer_id" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}customer_id=c_demo_001"
        return self.client.get(url, *args, **kwargs)

    def post(self, url, *args, **kwargs):
        if "/api/v1/cart/" in url and "customer_id" not in url and not url.endswith("/checkout"):
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}customer_id=c_demo_001"
        return self.client.post(url, *args, **kwargs)

    def patch(self, url, *args, **kwargs):
        if "/api/v1/cart/" in url and "customer_id" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}customer_id=c_demo_001"
        return self.client.patch(url, *args, **kwargs)

    def delete(self, url, *args, **kwargs):
        if "/api/v1/cart/" in url and "customer_id" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}customer_id=c_demo_001"
        return self.client.delete(url, *args, **kwargs)

client = ClientWrapper(TestClient(app))


def test_checkout_validation_empty_cart() -> None:
    # Create cart
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    assert create_res.status_code == 201
    cart_id = create_res.json()["cart_id"]

    # Checkout empty cart
    checkout_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
        "payment_method": "mock_upi",
        "customer_id": "c_demo_001"
    })
    assert checkout_res.status_code == 400
    assert "cart is empty" in checkout_res.json()["detail"].lower()


def test_checkout_invalid_cart_id() -> None:
    checkout_res = client.post("/api/v1/cart/cart_non_existent/checkout", json={
        "payment_method": "mock_upi",
        "customer_id": "c_demo_001"
    })
    assert checkout_res.status_code == 404
    assert "not found" in checkout_res.json()["detail"].lower()


def test_checkout_customer_mismatch() -> None:
    # Create cart for c_demo_001
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # Add item so it's not empty
    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })

    # Checkout with c_demo_999 (mismatch)
    checkout_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
        "payment_method": "mock_upi",
        "customer_id": "c_demo_999"
    })
    assert checkout_res.status_code in (400, 403)
    assert any(term in checkout_res.json()["detail"].lower() for term in ("customer id", "access denied", "permission"))


def test_checkout_insufficient_inventory() -> None:
    # Create cart
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # Add product AeroRun X1 (ur_shoe_001) with valid quantity
    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })

    # Manually modify the cart item quantity to exceed stock or bypass add validation
    # Let's bypass by trying to update quantity to 100 via PATCH
    update_res = client.patch(f"/api/v1/cart/{cart_id}/items/ur_shoe_001", json={
        "quantity": 100
    })
    assert update_res.status_code == 400  # Should be rejected on update as well


def test_successful_checkout_and_idempotency() -> None:
    # 1. Capture initial inventory of AeroRun X1
    products = _load_products()
    initial_qty = products["ur_shoe_001"].inventory_quantity

    # 2. Create cart
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # Add AeroRun X1 (₹4499)
    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 2
    })

    # 3. Checkout
    checkout_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
        "payment_method": "mock_upi",
        "customer_id": "c_demo_001"
    })
    assert checkout_res.status_code == 200
    order_data = checkout_res.json()

    assert order_data["order_id"].startswith("ord_")
    assert order_data["cart_id"] == cart_id
    assert order_data["customer_id"] == "c_demo_001"
    assert order_data["merchant_id"] == "m_urbanrun"
    assert order_data["total"] == 4499 * 2  # Shipping is free for >= 5000 subtotal, wait: 4499 * 2 = 8998 (Free Shipping)
    assert order_data["payment_status"] == "successful"
    assert order_data["payment_method"] == "mock_upi"
    assert order_data["payment_id"].startswith("pay_")
    assert order_data["transaction_reference"].startswith("txn_")
    assert len(order_data["items"]) == 1
    assert order_data["items"][0]["product_id"] == "ur_shoe_001"
    assert order_data["items"][0]["quantity"] == 2
    assert order_data["items"][0]["unit_price"] == 4499

    # 4. Check cart is now checked_out
    cart_res = client.get(f"/api/v1/cart/{cart_id}")
    assert cart_res.json()["status"] == "checked_out"

    # 5. Check inventory decremented exactly once
    products_after = _load_products()
    assert products_after["ur_shoe_001"].inventory_quantity == initial_qty - 2

    # 6. Idempotency test: duplicate checkout
    checkout_dup_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
        "payment_method": "mock_upi",
        "customer_id": "c_demo_001"
    })
    assert checkout_dup_res.status_code == 200
    assert checkout_dup_res.json()["order_id"] == order_data["order_id"]

    # Verify inventory is NOT decremented again
    products_after_dup = _load_products()
    assert products_after_dup["ur_shoe_001"].inventory_quantity == initial_qty - 2

    # 7. Get order via API
    get_order_res = client.get(f"/api/v1/checkout/order/{order_data['order_id']}?customer_id=c_demo_001")
    assert get_order_res.status_code == 200
    assert get_order_res.json()["order_id"] == order_data["order_id"]

    # Get order by cart
    get_order_by_cart_res = client.get(f"/api/v1/checkout/order/by-cart/{cart_id}?customer_id=c_demo_001")
    assert get_order_by_cart_res.status_code == 200
    assert get_order_by_cart_res.json()["order_id"] == order_data["order_id"]

    # Restore inventory
    from app.services.catalog_service import increment_inventory
    increment_inventory({"ur_shoe_001": 2})


def test_agent_checkout_safety_confirmation() -> None:
    graph = build_buyer_graph()

    # Step 1: User says "checkout my cart".
    # Since they haven't confirmed yet, the agent should fetch cart and ask for confirmation
    # Let's create a cart and add an item first so get_cart returns it
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]
    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })

    state = BuyerAgentState(
        session_id="test-session-checkout",
        customer_id="c_demo_001",
        cart_id=cart_id,
        user_message="Checkout my cart.",
        messages=[
            {
                "role": "user",
                "content": "Checkout my cart.",
            }
        ]
    )

    result = graph.invoke(state)
    # The agent should NOT checkout yet. It should ask for confirmation
    assert "Would you like me to place the order?" in result["final_response"]
    assert result["last_tool_result"] is not None
    assert result["last_tool_result"]["tool_name"] == "get_cart"

    # Step 2: User responds "yes"
    state_confirm = BuyerAgentState(
        session_id="test-session-checkout",
        customer_id="c_demo_001",
        cart_id=cart_id,
        user_message="Yes, place it.",
        messages=result["messages"] + [
            {
                "role": "user",
                "content": "Yes, place it.",
            }
        ]
    )

    result_confirm = graph.invoke(state_confirm)
    # Now it should call checkout_cart
    assert result_confirm["last_tool_result"] is not None
    assert result_confirm["last_tool_result"]["tool_name"] == "checkout_cart"
    assert "Order placed successfully" in result_confirm["final_response"]


def test_agent_get_order_status() -> None:
    graph = build_buyer_graph()

    # Create cart and checkout first
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]
    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })
    checkout_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
        "payment_method": "mock_upi",
        "customer_id": "c_demo_001"
    })
    order_id = checkout_res.json()["order_id"]

    state = BuyerAgentState(
        session_id="test-session-order",
        customer_id="c_demo_001",
        cart_id=cart_id,
        user_message="What did I just buy?",
        messages=[
            {
                "role": "user",
                "content": "What did I just buy?",
            }
        ]
    )

    result = graph.invoke(state)
    assert result["last_tool_result"] is not None
    assert result["last_tool_result"]["tool_name"] == "get_order"
    assert "ur_shoe_001" in result["final_response"] or "AeroRun" in result["final_response"]

    # Restore inventory
    from app.services.catalog_service import increment_inventory
    increment_inventory({"ur_shoe_001": 1})


def test_create_payment_order_endpoint_success_and_no_inventory_drain() -> None:
    # 1. Capture initial stock
    products = _load_products()
    initial_qty = products["ur_shoe_001"].inventory_quantity

    # 2. Create cart and add item
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })

    # 3. Call create-order endpoint
    order_res = client.post(f"/api/v1/cart/{cart_id}/payment/create-order", json={
        "customer_id": "c_demo_001"
    })
    assert order_res.status_code == 200
    data = order_res.json()

    assert "razorpay_order_id" in data
    assert data["amount_paise"] == data["total_inr"] * 100
    assert data["currency"] == "INR"
    assert data["cart_id"] == cart_id
    assert "key_id" in data

    # 4. Critical requirement: Inventory must NOT be decremented on order creation
    products_after = _load_products()
    assert products_after["ur_shoe_001"].inventory_quantity == initial_qty


def test_checkout_razorpay_verified_payment_flow() -> None:
    import hashlib
    import hmac
    from app.config import get_settings

    settings = get_settings()
    secret = "test_rzp_secret_key_789"

    with patch.object(settings, "razorpay_key_id", "rzp_test_key_abc"), \
         patch.object(settings, "razorpay_key_secret", secret):

        _load_products.cache_clear()
        products = _load_products()
        initial_qty = products["ur_shoe_001"].inventory_quantity

        # 1. Create cart
        create_res = client.post("/api/v1/cart", json={
            "merchant_id": "m_urbanrun",
            "customer_id": "c_demo_001"
        })
        cart_id = create_res.json()["cart_id"]

        client.post(f"/api/v1/cart/{cart_id}/items", json={
            "product_id": "ur_shoe_001",
            "quantity": 1
        })

        # 2. Dynamic unique Razorpay order and payment IDs
        import uuid
        rzp_order_id = f"order_rzp_test_{uuid.uuid4().hex[:8]}"
        rzp_payment_id = f"pay_rzp_test_{uuid.uuid4().hex[:8]}"

        # 3. Generate valid HMAC-SHA256 signature
        msg = f"{rzp_order_id}|{rzp_payment_id}"
        valid_sig = hmac.new(
            secret.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # 4. Checkout with valid signature
        checkout_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
            "payment_method": "razorpay",
            "customer_id": "c_demo_001",
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": rzp_payment_id,
            "razorpay_signature": valid_sig,
        })
        assert checkout_res.status_code == 200
        order_data = checkout_res.json()

        assert order_data["order_id"].startswith("ord_")
        assert order_data["payment_method"] == "razorpay"
        assert order_data["payment_status"] == "successful"
        assert order_data["payment_id"] == rzp_payment_id
        assert order_data["transaction_reference"] == rzp_order_id

        # 5. Inventory must be decremented by 1
        products_after = _load_products()
        assert products_after["ur_shoe_001"].inventory_quantity == initial_qty - 1

        # 6. Duplicate callback idempotency: Same payment ID submitted again returns existing order
        dup_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
            "payment_method": "razorpay",
            "customer_id": "c_demo_001",
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": rzp_payment_id,
            "razorpay_signature": valid_sig,
        })
        assert dup_res.status_code == 200
        assert dup_res.json()["order_id"] == order_data["order_id"]

        # Inventory NOT decremented again
        products_after_dup = _load_products()
        assert products_after_dup["ur_shoe_001"].inventory_quantity == initial_qty - 1

        # Restore inventory for other tests
        from app.services.catalog_service import increment_inventory
        increment_inventory({"ur_shoe_001": 1})


def test_checkout_razorpay_invalid_signature_rejected() -> None:
    from app.config import get_settings

    settings = get_settings()
    with patch.object(settings, "razorpay_key_id", "rzp_test_key_abc"), \
         patch.object(settings, "razorpay_key_secret", "real_secret_123"):

        _load_products.cache_clear()
        products = _load_products()
        initial_qty = products["ur_shoe_001"].inventory_quantity

        create_res = client.post("/api/v1/cart", json={
            "merchant_id": "m_urbanrun",
            "customer_id": "c_demo_001"
        })
        cart_id = create_res.json()["cart_id"]

        client.post(f"/api/v1/cart/{cart_id}/items", json={
            "product_id": "ur_shoe_001",
            "quantity": 1
        })

        # Checkout with forged/invalid signature
        checkout_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
            "payment_method": "razorpay",
            "customer_id": "c_demo_001",
            "razorpay_order_id": "order_123",
            "razorpay_payment_id": "pay_123",
            "razorpay_signature": "forged_invalid_signature",
        })
        assert checkout_res.status_code == 400
        assert "invalid razorpay payment signature" in checkout_res.json()["detail"].lower()

        # Stock must NOT be decremented
        products_after = _load_products()
        assert products_after["ur_shoe_001"].inventory_quantity == initial_qty


def test_checkout_razorpay_missing_parameters_rejected() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })

    # Missing signature and payment ID
    checkout_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={
        "payment_method": "razorpay",
        "customer_id": "c_demo_001",
    })
    assert checkout_res.status_code == 400
    assert "razorpay payment verification requires" in checkout_res.json()["detail"].lower()


def test_razorpay_duplicate_payment_confirmation_idempotency() -> None:
    """
    Simulates the exact same Razorpay payment confirmation arriving twice (e.g. duplicate webhook/callback or client retry).
    Asserts:
    1. Exactly ONE order exists in the database.
    2. Inventory is decremented exactly ONCE.
    3. The second callback returns the existing order and does not create another order.
    4. The second callback does not decrement inventory again.
    """
    import hashlib
    import hmac
    import uuid
    from app.config import get_settings
    from app.services.catalog_service import increment_inventory

    settings = get_settings()
    secret = "rzp_idempotency_secret_key"

    with patch.object(settings, "razorpay_key_id", "rzp_test_key_idem"), \
         patch.object(settings, "razorpay_key_secret", secret):

        _load_products.cache_clear()
        initial_qty = _load_products()["ur_shoe_001"].inventory_quantity

        # 1. Create cart and add 2 units
        create_res = client.post("/api/v1/cart", json={
            "merchant_id": "m_urbanrun",
            "customer_id": "c_demo_001"
        })
        assert create_res.status_code == 201
        cart_id = create_res.json()["cart_id"]

        add_res = client.post(f"/api/v1/cart/{cart_id}/items", json={
            "product_id": "ur_shoe_001",
            "quantity": 2
        })
        assert add_res.status_code == 200

        # 2. Prepare deterministic Razorpay confirmation parameters
        rzp_order_id = f"order_rzp_idem_{uuid.uuid4().hex[:8]}"
        rzp_payment_id = f"pay_rzp_idem_{uuid.uuid4().hex[:8]}"
        msg = f"{rzp_order_id}|{rzp_payment_id}"
        valid_sig = hmac.new(
            secret.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        payload = {
            "payment_method": "razorpay",
            "customer_id": "c_demo_001",
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": rzp_payment_id,
            "razorpay_signature": valid_sig,
        }

        try:
            # 3. First payment confirmation / callback arrives
            first_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json=payload)
            assert first_res.status_code == 200
            first_order = first_res.json()
            first_order_id = first_order["order_id"]
            assert first_order_id.startswith("ord_")
            assert first_order["payment_id"] == rzp_payment_id

            # Assert inventory decremented exactly once (by 2)
            qty_after_first = _load_products()["ur_shoe_001"].inventory_quantity
            assert qty_after_first == initial_qty - 2

            # 4. Duplicate payment confirmation / callback arrives with same payment ID and cart
            second_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json=payload)
            assert second_res.status_code == 200
            second_order = second_res.json()

            # Assert second callback returned the existing order without creating a new one
            assert second_order["order_id"] == first_order_id
            assert second_order["payment_id"] == rzp_payment_id

            # 5. Verify database records: exactly ONE order exists for this cart and payment
            db = SessionLocal()
            try:
                orders_for_cart = db.query(Order).filter(Order.cart_id == cart_id).all()
                assert len(orders_for_cart) == 1
                assert orders_for_cart[0].order_id == first_order_id

                orders_for_payment = db.query(Order).filter(Order.payment_id == rzp_payment_id).all()
                assert len(orders_for_payment) == 1
                assert orders_for_payment[0].order_id == first_order_id
            finally:
                db.close()

            # 6. Assert inventory was NOT decremented again
            qty_after_second = _load_products()["ur_shoe_001"].inventory_quantity
            assert qty_after_second == initial_qty - 2
        finally:
            # Restore inventory for clean test state
            increment_inventory({"ur_shoe_001": 2})
