import os
os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.models import Cart, CartItem, Order, OrderItem
from app.db.database import SessionLocal, init_db
from app.agents.graph import build_buyer_graph
from app.agents.state import BuyerAgentState
from app.tools.cart_tools import get_cart, add_to_cart, remove_from_cart, update_cart_item
from app.tools.payment_tools import get_order, get_order_tracking, cancel_order, request_return, checkout_cart

client = TestClient(app)


def setup_test_data():
    init_db()
    db = SessionLocal()
    try:
        # Clean up any existing records for test customers
        db.query(OrderItem).filter(OrderItem.order_id.in_(["ord_b_100", "ord_a_100"])).delete(synchronize_session=False)
        db.query(Order).filter(Order.order_id.in_(["ord_b_100", "ord_a_100"])).delete(synchronize_session=False)
        db.query(CartItem).filter(CartItem.cart_id.in_(["cart_cust_b_100", "cart_cust_a_100"])).delete(synchronize_session=False)
        db.query(Cart).filter(Cart.id.in_(["cart_cust_b_100", "cart_cust_a_100"])).delete(synchronize_session=False)
        db.commit()

        # Create Cart and Order for Customer B (Target of attacks)
        cart_b = Cart(
            id="cart_cust_b_100",
            merchant_id="m_urbanrun",
            customer_id="customer_b",
            currency="INR",
            status="active",
            subtotal_inr=4499,
            discount_inr=0,
            shipping_inr=0,
            total_inr=4499,
            applied_offers_json="[]",
        )
        item_b = CartItem(
            cart_id="cart_cust_b_100",
            product_id="ur_shoe_001",
            sku="UR-RS-001",
            name="AeroRun X1",
            unit_price_inr=4499,
            quantity=1,
            line_total_inr=4499,
            available=True,
            inventory_checked=True,
        )
        cart_b.items.append(item_b)
        db.add(cart_b)

        order_b = Order(
            order_id="ord_b_100",
            cart_id="cart_cust_b_100",
            customer_id="customer_b",
            merchant_id="m_urbanrun",
            currency="INR",
            subtotal=4499,
            discount=0,
            shipping=0,
            total=4499,
            status="placed",
            payment_status="successful",
            payment_id="pay_b_100",
            payment_method="mock_upi",
        )
        db.add(order_b)
        db.commit()
    finally:
        db.close()


def test_adversarial_cart_isolation_via_api():
    setup_test_data()

    # Attack 1: Customer A fetches Customer B's cart
    res = client.get("/api/v1/cart/cart_cust_b_100?customer_id=customer_a")
    assert res.status_code == 403

    # Attack 2: Customer A adds to Customer B's cart
    res = client.post(
        "/api/v1/cart/cart_cust_b_100/items?customer_id=customer_a",
        json={"product_id": "ur_shoe_002", "quantity": 1},
    )
    assert res.status_code == 403

    # Attack 3: Customer A modifies Customer B's cart item
    res = client.patch(
        "/api/v1/cart/cart_cust_b_100/items/ur_shoe_001?customer_id=customer_a",
        json={"quantity": 3},
    )
    assert res.status_code == 403

    # Attack 4: Customer A removes item from Customer B's cart
    res = client.delete(
        "/api/v1/cart/cart_cust_b_100/items/ur_shoe_001?customer_id=customer_a"
    )
    assert res.status_code == 403

    # Attack 5: Customer A checks out Customer B's cart
    res = client.post(
        "/api/v1/cart/cart_cust_b_100/checkout",
        json={"payment_method": "mock_upi", "customer_id": "customer_a"},
    )
    assert res.status_code in (400, 403)


def test_adversarial_order_isolation_via_api():
    setup_test_data()

    # Attack 6: Customer A fetches Customer B's order
    res = client.get("/api/v1/checkout/order/ord_b_100?customer_id=customer_a")
    assert res.status_code == 403

    # Attack 7: Customer A tracks Customer B's order
    res = client.get("/api/v1/checkout/order/ord_b_100/tracking?customer_id=customer_a")
    assert res.status_code == 403

    # Attack 8: Customer A cancels Customer B's order
    res = client.post(
        "/api/v1/checkout/order/ord_b_100/cancel",
        json={"customer_id": "customer_a"},
    )
    assert res.status_code == 403

    # Attack 9: Customer A requests return on Customer B's order
    res = client.post(
        "/api/v1/checkout/order/ord_b_100/return",
        json={"product_id": "ur_shoe_001", "quantity": 1, "customer_id": "customer_a"},
    )
    assert res.status_code == 403


def test_adversarial_tools_isolation():
    setup_test_data()

    # Direct tool call with mismatched customer_id
    with pytest.raises((ValueError, PermissionError)):
        get_cart(cart_id="cart_cust_b_100", customer_id="customer_a")

    with pytest.raises((ValueError, PermissionError)):
        add_to_cart(cart_id="cart_cust_b_100", product_id="ur_shoe_002", quantity=1, customer_id="customer_a")

    with pytest.raises((ValueError, PermissionError)):
        update_cart_item(cart_id="cart_cust_b_100", product_id="ur_shoe_001", quantity=5, customer_id="customer_a")

    with pytest.raises((ValueError, PermissionError)):
        remove_from_cart(cart_id="cart_cust_b_100", product_id="ur_shoe_001", customer_id="customer_a")

    with pytest.raises((ValueError, PermissionError)):
        get_order(order_id="ord_b_100", customer_id="customer_a")

    with pytest.raises((ValueError, PermissionError)):
        get_order_tracking(order_id="ord_b_100", customer_id="customer_a")

    with pytest.raises((ValueError, PermissionError)):
        cancel_order(order_id="ord_b_100", customer_id="customer_a")

    with pytest.raises((ValueError, PermissionError)):
        request_return(order_id="ord_b_100", product_id="ur_shoe_001", quantity=1, customer_id="customer_a")
