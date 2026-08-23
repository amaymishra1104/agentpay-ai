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
