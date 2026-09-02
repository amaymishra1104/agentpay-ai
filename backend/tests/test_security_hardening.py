import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.database import SessionLocal, init_db
from app.db.models import Cart, CartItem, Order, OrderItem, PaymentOrder, WebhookEvent, OrderConfirmation
from app.main import app
from app.services.auth_service import create_session_token, verify_session_token
from app.services.catalog_service import _load_products, increment_inventory, decrement_inventory
from app.services.confirmation_service import compute_cart_hash, request_cart_confirmation, verify_order_confirmation

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    init_db()
    db = SessionLocal()
    try:
        db.query(WebhookEvent).delete()
        db.query(OrderConfirmation).delete()
        db.query(OrderItem).delete()
        db.query(Order).delete()
        db.query(PaymentOrder).delete()
        db.query(CartItem).delete()
        db.query(Cart).delete()
        db.commit()
    finally:
        db.close()


def get_auth_headers(customer_id: str) -> dict:
    token = create_session_token(customer_id)
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# 1. SERVER-AUTHORITATIVE CUSTOMER IDENTITY & SESSION TOKEN SECURITY
# ==============================================================================

def test_auth_session_endpoint_issue_token():
    res = client.post("/api/v1/auth/session", json={"customer_id": "c_sec_001"})
    assert res.status_code == 200
    data = res.json()
    assert data["customer_id"] == "c_sec_001"
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0

    # Verify token payload
    verified_payload = verify_session_token(data["access_token"])
    assert verified_payload["customer_id"] == "c_sec_001"


def test_auth_me_endpoint():
    headers = get_auth_headers("c_sec_001")
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 200
    assert res.json()["customer_id"] == "c_sec_001"
    assert res.json()["authenticated"] is True


def test_missing_session_token_rejected_with_401():
    # Cart creation without token
    res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun", "customer_id": "c_sec_001"})
    assert res.status_code == 401
    assert "authentication required" in res.json()["detail"].lower()

    # Get cart without token
    res = client.get("/api/v1/cart/cart_some_id")
    assert res.status_code == 401


def test_forged_and_tampered_token_signature_rejected_with_401():
    token = create_session_token("c_sec_001")
    # Tamper payload
    parts = token.split(".")
    tampered_token = f"forged_payload.{parts[1]}"

    res = client.get("/api/v1/cart/cart_test", headers={"Authorization": f"Bearer {tampered_token}"})
    assert res.status_code == 401
    assert "invalid or tampered" in res.json()["detail"].lower()


def test_expired_token_rejected_with_401():
    import base64
    settings = get_settings()
    now_ts = int(time.time()) - 3600  # 1 hour in the past
    payload = {
        "customer_id": "c_sec_001",
        "iat": now_ts - 7200,
        "exp": now_ts,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")
    sig = hmac.new(settings.session_secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    expired_token = f"{payload_b64}.{sig_b64}"

    res = client.get("/api/v1/cart/cart_test", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower()


def test_client_cannot_impersonate_by_overriding_payload_customer_id():
    """
    Attacker is authenticated as 'attacker_001' but sends 'customer_id': 'victim_001' in request body.
    Server MUST create the cart bound to 'attacker_001'.
    """
    headers = get_auth_headers("attacker_001")
    res = client.post(
        "/api/v1/cart",
        json={"merchant_id": "m_urbanrun", "customer_id": "victim_001"},
        headers=headers,
    )
    assert res.status_code == 201
    assert res.json()["customer_id"] == "attacker_001"
    assert res.json()["customer_id"] != "victim_001"


# ==============================================================================
# 2. CROSS-TENANT ISOLATION & RESOURCE OWNERSHIP (CARTS & ORDERS)
# ==============================================================================

def test_cross_tenant_cart_manipulation_prevented():
    # Customer A creates Cart A
    headers_a = get_auth_headers("customer_a")
    headers_b = get_auth_headers("customer_b")

    cart_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers_a)
    assert cart_res.status_code == 201
    cart_id = cart_res.json()["cart_id"]

    # Customer B attempts GET
    res = client.get(f"/api/v1/cart/{cart_id}", headers=headers_b)
    assert res.status_code == 403

    # Customer B attempts to add items to Customer A's cart
    res = client.post(f"/api/v1/cart/{cart_id}/items", json={"product_id": "ur_shoe_001", "quantity": 1}, headers=headers_b)
    assert res.status_code == 403

    # Customer B attempts to clear Customer A's cart
    res = client.delete(f"/api/v1/cart/{cart_id}", headers=headers_b)
    assert res.status_code == 403

    # Customer B attempts to checkout Customer A's cart
    res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={"payment_method": "mock_upi"}, headers=headers_b)
    assert res.status_code == 403


def test_cross_tenant_order_manipulation_prevented():
    headers_a = get_auth_headers("customer_a")
    headers_b = get_auth_headers("customer_b")

    # Customer A creates cart and checks out
    cart_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers_a)
    cart_id = cart_res.json()["cart_id"]
    client.post(f"/api/v1/cart/{cart_id}/items", json={"product_id": "ur_shoe_001", "quantity": 1}, headers=headers_a)

    chk_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={"payment_method": "mock_upi"}, headers=headers_a)
    assert chk_res.status_code == 200
    order_id = chk_res.json()["order_id"]

    # Customer B cannot GET order
    res = client.get(f"/api/v1/checkout/order/{order_id}", headers=headers_b)
    assert res.status_code == 403

    # Customer B cannot get tracking
    res = client.get(f"/api/v1/checkout/order/{order_id}/tracking", headers=headers_b)
    assert res.status_code == 403

    # Customer B CANNOT advance order status
    res = client.post(f"/api/v1/checkout/order/{order_id}/advance-status", headers=headers_b)
    assert res.status_code == 403

    # Customer B cannot cancel order
    res = client.post(f"/api/v1/checkout/order/{order_id}/cancel", headers=headers_b)
    assert res.status_code == 403

    # Owner (Customer A) CAN advance status
    res = client.post(f"/api/v1/checkout/order/{order_id}/advance-status", headers=headers_a)
    assert res.status_code == 200
    assert res.json()["status"] == "confirmed"

    # Restore inventory
    increment_inventory({"ur_shoe_001": 1})


# ==============================================================================
# 3. RAZORPAY PAYMENT-ORDER BINDING & CART SUBSTITUTION ATTACKS
# ==============================================================================

def test_cart_substitution_attack_rejected():
    """
    ATTACK SCENARIO:
    1. Attacker creates Cart 1 for ₹299 (AeroGrip Socks or small item).
    2. Attacker initiates payment order for Cart 1 -> receives valid razorpay_order_id for ₹299.
    3. Attacker creates Cart 2 for ₹8,998 (2x AeroRun X1 shoes).
    4. Attacker attempts to checkout Cart 2 using the razorpay_order_id and valid signature for Cart 1!
    5. EXPECTED: Server MUST REJECT with 400 Bad Request (Payment order does not match current cart).
    """
    headers = get_auth_headers("c_attacker_sub")

    # Cart 1: Small item ₹299 + ₹150 shipping = ₹449
    cart1_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers)
    cart1_id = cart1_res.json()["cart_id"]
    client.post(f"/api/v1/cart/{cart1_id}/items", json={"product_id": "ur_sock_001", "quantity": 1}, headers=headers)

    # Create PaymentOrder for Cart 1
    p_res1 = client.post(f"/api/v1/cart/{cart1_id}/payment/create-order", headers=headers)
    assert p_res1.status_code == 200
    rzp_order_id_1 = p_res1.json()["razorpay_order_id"]

    # Cart 2: Expensive item ₹4499 + ₹4499 = ₹8998
    cart2_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers)
    cart2_id = cart2_res.json()["cart_id"]
    client.post(f"/api/v1/cart/{cart2_id}/items", json={"product_id": "ur_shoe_001", "quantity": 2}, headers=headers)

    # Generate signature for Cart 1's payment order
    rzp_payment_id = f"pay_sub_{uuid.uuid4().hex[:8]}"
    msg = f"{rzp_order_id_1}|{rzp_payment_id}"
    valid_sig = hmac.new("rzp_test_secret_placeholder".encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()

    # Attempt to checkout Cart 2 using Cart 1's payment order!
    checkout_res = client.post(
        f"/api/v1/cart/{cart2_id}/checkout",
        json={
            "payment_method": "razorpay",
            "razorpay_order_id": rzp_order_id_1,
            "razorpay_payment_id": rzp_payment_id,
            "razorpay_signature": valid_sig,
        },
        headers=headers,
    )
    assert checkout_res.status_code == 400
    err_detail = checkout_res.json()["detail"].lower()
    assert "cart" in err_detail or "match" in err_detail or "tamper" in err_detail or "amount" in err_detail


def test_cross_customer_payment_order_usage_rejected():
    """Customer A creates a payment order; Customer B cannot use it."""
    headers_a = get_auth_headers("customer_a")
    headers_b = get_auth_headers("customer_b")

    cart_a = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers_a).json()["cart_id"]
    client.post(f"/api/v1/cart/{cart_a}/items", json={"product_id": "ur_shoe_001", "quantity": 1}, headers=headers_a)
    p_res = client.post(f"/api/v1/cart/{cart_a}/payment/create-order", headers=headers_a)
    rzp_order_id = p_res.json()["razorpay_order_id"]

    cart_b = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers_b).json()["cart_id"]
    client.post(f"/api/v1/cart/{cart_b}/items", json={"product_id": "ur_shoe_001", "quantity": 1}, headers=headers_b)

    rzp_payment_id = f"pay_x_{uuid.uuid4().hex[:8]}"
    msg = f"{rzp_order_id}|{rzp_payment_id}"
    sig = hmac.new("rzp_test_secret_placeholder".encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()

    checkout_res = client.post(
        f"/api/v1/cart/{cart_b}/checkout",
        json={
            "payment_method": "razorpay",
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": rzp_payment_id,
            "razorpay_signature": sig,
        },
        headers=headers_b,
    )
    assert checkout_res.status_code in (400, 403)


# ==============================================================================
# 4. AUTHORITATIVE WEBHOOK PROCESSING & SIGNATURE VALIDATION
# ==============================================================================

def test_webhook_missing_signature_rejected():
    res = client.post("/api/v1/webhooks/razorpay", json={"event": "payment.captured"})
    assert res.status_code == 400
    assert "signature" in res.json()["detail"].lower()


def test_webhook_invalid_signature_rejected():
    res = client.post(
        "/api/v1/webhooks/razorpay",
        json={"event": "payment.captured"},
        headers={"X-Razorpay-Signature": "invalid_forged_sig"},
    )
    assert res.status_code == 400
    assert "signature" in res.json()["detail"].lower()


def test_webhook_payment_captured_and_idempotency():
    headers = get_auth_headers("c_webhook_cust")
    settings = get_settings()
    secret = "webhook_secret_xyz_123"

    with patch.object(settings, "webhook_secret", secret):
        # 1. Create cart and payment order
        cart_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers)
        cart_id = cart_res.json()["cart_id"]
        client.post(f"/api/v1/cart/{cart_id}/items", json={"product_id": "ur_shoe_001", "quantity": 1}, headers=headers)

        p_res = client.post(f"/api/v1/cart/{cart_id}/payment/create-order", headers=headers)
        rzp_order_id = p_res.json()["razorpay_order_id"]
        rzp_payment_id = f"pay_wh_{uuid.uuid4().hex[:8]}"

        # 2. Build payment.captured webhook payload
        event_id = f"evt_{uuid.uuid4().hex}"
        payload_dict = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": rzp_payment_id,
                        "order_id": rzp_order_id,
                        "amount": 449900,
                        "currency": "INR",
                        "status": "captured",
                        "method": "card",
                        "notes": {
                            "cart_id": cart_id,
                            "customer_id": "c_webhook_cust",
                        },
                    }
                }
            }
        }
        raw_body = json.dumps(payload_dict, separators=(",", ":"))
        sig = hmac.new(secret.encode("utf-8"), raw_body.encode("utf-8"), hashlib.sha256).hexdigest()

        # 3. Deliver webhook
        wh_res = client.post(
            "/api/v1/webhooks/razorpay",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
                "X-Razorpay-Event-Id": event_id,
            },
        )
        assert wh_res.status_code == 200
        assert wh_res.json()["status"] == "processed"
        assert wh_res.json()["event_id"] == event_id

        # 4. Deliver duplicate webhook (Replay Attack / Retry)
        wh_dup_res = client.post(
            "/api/v1/webhooks/razorpay",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
                "X-Razorpay-Event-Id": event_id,
            },
        )
        assert wh_dup_res.status_code == 200
        assert wh_dup_res.json()["status"] == "already_processed"


def test_webhook_refund_processed_restores_inventory():
    headers = get_auth_headers("c_refund_cust")
    settings = get_settings()
    secret = "wh_refund_sec"

    with patch.object(settings, "webhook_secret", secret):
        cart_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers)
        cart_id = cart_res.json()["cart_id"]
        client.post(f"/api/v1/cart/{cart_id}/items", json={"product_id": "ur_shoe_001", "quantity": 1}, headers=headers)

        chk_res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={"payment_method": "mock_upi"}, headers=headers)
        order_id = chk_res.json()["order_id"]
        payment_id = chk_res.json()["payment_id"]

        # Webhook refund.processed
        event_id = f"evt_ref_{uuid.uuid4().hex}"
        payload_dict = {
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": f"rfnd_{uuid.uuid4().hex[:8]}",
                        "payment_id": payment_id,
                        "amount": 449900,
                    }
                }
            }
        }
        raw_body = json.dumps(payload_dict, separators=(",", ":"))
        sig = hmac.new(secret.encode("utf-8"), raw_body.encode("utf-8"), hashlib.sha256).hexdigest()

        wh_res = client.post(
            "/api/v1/webhooks/razorpay",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
                "X-Razorpay-Event-Id": event_id,
            },
        )
        assert wh_res.status_code == 200
        assert wh_res.json()["status"] == "processed"

        # Check order status in db
        db = SessionLocal()
        try:
            ord_record = db.query(Order).filter(Order.order_id == order_id).first()
            assert ord_record.payment_status == "refunded"
            assert ord_record.status == "cancelled"
        finally:
            db.close()

        # Restore inventory for clean tests
        increment_inventory({"ur_shoe_001": 1})


# ==============================================================================
# 5. SPENDING LIMITS (TRANSACTION & DAILY)
# ==============================================================================

def test_per_transaction_spending_limit():
    headers = get_auth_headers("c_spend_tx")

    # 1. Under ₹80,000 limit (3 AeroRun X1 = ₹13,497) -> Checkout allowed
    cart_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers)
    cart_id = cart_res.json()["cart_id"]
    client.post(f"/api/v1/cart/{cart_id}/items", json={"product_id": "ur_shoe_001", "quantity": 3}, headers=headers)

    res = client.post(f"/api/v1/cart/{cart_id}/checkout", json={"payment_method": "mock_upi"}, headers=headers)
    assert res.status_code == 200

    # 2. Exceeding ₹80,000 limit: 10 ur_shoe_002 (₹59,990) + 5 ur_shoe_005 (₹34,995) = ₹94,985 -> Rejected with 400
    cart2_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers)
    cart2_id = cart2_res.json()["cart_id"]
    client.post(f"/api/v1/cart/{cart2_id}/items", json={"product_id": "ur_shoe_002", "quantity": 10}, headers=headers)
    client.post(f"/api/v1/cart/{cart2_id}/items", json={"product_id": "ur_shoe_005", "quantity": 5}, headers=headers)

    res2 = client.post(f"/api/v1/cart/{cart2_id}/checkout", json={"payment_method": "mock_upi"}, headers=headers)
    assert res2.status_code == 400
    assert "exceeds the maximum allowed transaction limit" in res2.json()["detail"].lower()

    # Restore inventory
    increment_inventory({"ur_shoe_001": 3})


def test_daily_spending_limit():
    headers = get_auth_headers("c_spend_daily")

    # Order 1: 5 * ur_shoe_002 (₹29,995)
    c1_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers)
    c1_id = c1_res.json()["cart_id"]
    client.post(f"/api/v1/cart/{c1_id}/items", json={"product_id": "ur_shoe_002", "quantity": 5}, headers=headers)
    res1 = client.post(f"/api/v1/cart/{c1_id}/checkout", json={"payment_method": "mock_upi"}, headers=headers)
    assert res1.status_code == 200

    # Order 2: 10 * ur_shoe_003 (₹39,990) -> Total: ₹69,985
    c2_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers)
    c2_id = c2_res.json()["cart_id"]
    client.post(f"/api/v1/cart/{c2_id}/items", json={"product_id": "ur_shoe_003", "quantity": 10}, headers=headers)
    res2 = client.post(f"/api/v1/cart/{c2_id}/checkout", json={"payment_method": "mock_upi"}, headers=headers)
    assert res2.status_code == 200

    # Order 3: 15 * ur_shoe_003 (₹59,985) -> Total: ₹129,970 (< ₹200,000 daily limit)
    c3_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers)
    c3_id = c3_res.json()["cart_id"]
    client.post(f"/api/v1/cart/{c3_id}/items", json={"product_id": "ur_shoe_003", "quantity": 15}, headers=headers)
    res3 = client.post(f"/api/v1/cart/{c3_id}/checkout", json={"payment_method": "mock_upi"}, headers=headers)
    assert res3.status_code == 200

    # Order 4: 11 * ur_shoe_005 (₹76,989 <= ₹80,000 per-tx limit) -> Total: 129,970 + 76,989 = ₹206,959 (> ₹200,000 daily limit)
    c4_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers)
    c4_id = c4_res.json()["cart_id"]
    client.post(f"/api/v1/cart/{c4_id}/items", json={"product_id": "ur_shoe_005", "quantity": 11}, headers=headers)
    res4 = client.post(f"/api/v1/cart/{c4_id}/checkout", json={"payment_method": "mock_upi"}, headers=headers)
    assert res4.status_code == 400
    assert "exceeds your daily spending limit of ₹200,000" in res4.json()["detail"]

    # Restore inventory
    increment_inventory({"ur_shoe_002": 5, "ur_shoe_003": 25})


# ==============================================================================
# 6. HUMAN CONFIRMATION GATE
# ==============================================================================

def test_confirmation_gate_workflow_and_tamper_invalidation():
    headers = get_auth_headers("c_confirm_cust")

    # 1. Create cart and add item
    cart_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers)
    cart_id = cart_res.json()["cart_id"]
    client.post(f"/api/v1/cart/{cart_id}/items", json={"product_id": "ur_shoe_001", "quantity": 1}, headers=headers)

    # 2. Request human confirmation
    conf_res = client.post(f"/api/v1/cart/{cart_id}/confirm", headers=headers)
    assert conf_res.status_code == 200
    conf_data = conf_res.json()
    assert conf_data["confirmation_id"].startswith("conf_")
    assert conf_data["cart_hash"]
    assert conf_data["status"] == "approved"
    conf_id = conf_data["confirmation_id"]

    # 3. Tamper cart: Add another item after approval!
    client.post(f"/api/v1/cart/{cart_id}/items", json={"product_id": "ur_sock_001", "quantity": 1}, headers=headers)

    # 4. Attempt checkout with the stale confirmation_id
    chk_res = client.post(
        f"/api/v1/cart/{cart_id}/checkout",
        json={"payment_method": "mock_upi", "confirmation_id": conf_id},
        headers=headers,
    )
    assert chk_res.status_code == 400
    assert "cart contents or total have changed" in chk_res.json()["detail"].lower()

    # 5. Request fresh confirmation on the modified cart
    conf2_res = client.post(f"/api/v1/cart/{cart_id}/confirm", headers=headers)
    assert conf2_res.status_code == 200
    conf2_id = conf2_res.json()["confirmation_id"]

    # 6. Checkout now succeeds
    chk2_res = client.post(
        f"/api/v1/cart/{cart_id}/checkout",
        json={"payment_method": "mock_upi", "confirmation_id": conf2_id},
        headers=headers,
    )
    assert chk2_res.status_code == 200

    # Restore inventory
    increment_inventory({"ur_shoe_001": 1, "ur_sock_001": 1})


def test_spending_limit_exact_boundaries():
    """
    Test exact boundary values for per-transaction limit:
    - ₹1       -> Allowed
    - ₹500     -> Allowed
    - ₹9,999   -> Allowed
    - ₹10,000  -> Allowed
    - ₹15,000  -> Allowed
    - ₹16,000  -> Allowed
    - ₹25,000  -> Allowed
    - ₹50,000  -> Allowed
    - ₹79,999  -> Allowed
    - ₹80,000  -> Allowed
    - ₹80,001  -> Rejected (SpendingLimitExceededError)
    """
    from app.services import spending_limit_service

    # Per-transaction boundaries (INR)
    allowed_amounts_inr = [1, 500, 9999, 10000, 15000, 16000, 25000, 50000, 79999, 80000]
    for amt in allowed_amounts_inr:
        spending_limit_service.check_transaction_limit(amt)

    # Over-limit boundary
    with pytest.raises(spending_limit_service.SpendingLimitExceededError):
        spending_limit_service.check_transaction_limit(80001)

    # Corresponding paise verification (where amount_paise = amount_inr * 100)
    for amt in allowed_amounts_inr:
        amt_paise = amt * 100
        spending_limit_service.check_transaction_limit(amt_paise // 100)

    over_paise = 8000100
    with pytest.raises(spending_limit_service.SpendingLimitExceededError):
        spending_limit_service.check_transaction_limit(over_paise // 100)

    # Daily spend limit boundaries against database
    db = SessionLocal()
    try:
        # Initial spend: 0. ₹200,000 transaction check -> Allowed
        spending_limit_service.check_daily_spend_limit("c_spend_bound", 200000, db)

        # ₹200,001 transaction check -> Exceeds daily limit
        with pytest.raises(spending_limit_service.SpendingLimitExceededError):
            spending_limit_service.check_daily_spend_limit("c_spend_bound", 200001, db)
    finally:
        db.close()


def test_confirmation_gate_expired_rejected():
    """
    Test that an expired confirmation token cannot be used to checkout.
    """
    headers = get_auth_headers("c_exp_conf")

    cart_res = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers)
    cart_id = cart_res.json()["cart_id"]
    client.post(f"/api/v1/cart/{cart_id}/items", json={"product_id": "ur_shoe_001", "quantity": 1}, headers=headers)

    conf_res = client.post(f"/api/v1/cart/{cart_id}/confirm", headers=headers)
    assert conf_res.status_code == 200
    conf_id = conf_res.json()["confirmation_id"]

    # Manually expire the confirmation in the database
    db = SessionLocal()
    try:
        conf_record = db.query(OrderConfirmation).filter(OrderConfirmation.confirmation_id == conf_id).first()
        assert conf_record is not None
        conf_record.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
        db.commit()
    finally:
        db.close()

    # Checkout with expired confirmation must fail with 400
    chk_res = client.post(
        f"/api/v1/cart/{cart_id}/checkout",
        json={"payment_method": "mock_upi", "confirmation_id": conf_id},
        headers=headers,
    )
    assert chk_res.status_code == 400
    assert "expired" in chk_res.json()["detail"].lower()


def test_confirmation_cross_customer_and_cross_cart_rejected():
    """
    Test that Customer B cannot use Customer A's confirmation token,
    and Cart B cannot use Cart A's confirmation token.
    """
    headers_a = get_auth_headers("c_conf_a")
    headers_b = get_auth_headers("c_conf_b")

    # Customer A cart
    cart_a = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers_a).json()["cart_id"]
    client.post(f"/api/v1/cart/{cart_a}/items", json={"product_id": "ur_shoe_001", "quantity": 1}, headers=headers_a)
    conf_a = client.post(f"/api/v1/cart/{cart_a}/confirm", headers=headers_a).json()["confirmation_id"]

    # Customer B cart
    cart_b = client.post("/api/v1/cart", json={"merchant_id": "m_urbanrun"}, headers=headers_b).json()["cart_id"]
    client.post(f"/api/v1/cart/{cart_b}/items", json={"product_id": "ur_shoe_001", "quantity": 1}, headers=headers_b)

    # Customer B tries to checkout Cart B using Customer A's confirmation token -> Rejected
    chk_b = client.post(
        f"/api/v1/cart/{cart_b}/checkout",
        json={"payment_method": "mock_upi", "confirmation_id": conf_a},
        headers=headers_b,
    )
    assert chk_b.status_code == 400
    assert "different customer" in chk_b.json()["detail"].lower() or "different cart" in chk_b.json()["detail"].lower()
